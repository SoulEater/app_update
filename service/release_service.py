"""发布版本服务层

负责版本状态机、流式产物上传、摘要复算、manifest 对比与发布/暂停编排
"""

import asyncio
import hashlib
import os

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.model import User
from backend.common.exception import errors
from backend.common.pagination import paging_data
from backend.plugin.app_update.config import app_update_settings as settings
from backend.plugin.app_update.crud.crud_application import application_dao
from backend.plugin.app_update.crud.crud_artifact import artifact_dao
from backend.plugin.app_update.crud.crud_channel import channel_dao
from backend.plugin.app_update.crud.crud_release import release_dao
from backend.plugin.app_update.enums import ArtifactKind, ReleaseStatus
from backend.plugin.app_update.model import Artifact, Release
from backend.plugin.app_update.schema.artifact import GetArtifactDetail, UploadArtifactResult
from backend.plugin.app_update.schema.release import (
    CreateReleaseParam,
    GetReleaseDetail,
    GetReleaseWithArtifactDetail,
    PauseReleaseResult,
    PublishReleaseResult,
    ReleaseSignatureInfo,
    UpdateReleaseParam,
)
from backend.plugin.app_update.utils.artifact_storage import artifact_storage, safe_filename
from backend.plugin.app_update.utils.manifest import parse_manifest, validate_release_manifest
from backend.plugin.app_update.utils.version import parse_version
from backend.utils.serializers import select_columns_serialize
from backend.utils.timezone import timezone

SUPPORTED_PLATFORM = 'win32'
SUPPORTED_ARCH = 'x64'


def artifact_name_prefix(*, application_key: str) -> str:
    """产物名前缀：应用 key 首字母大写，与前端上传校验、electron-builder 默认产物命名保持一致"""
    return application_key[:1].upper() + application_key[1:]


def installer_filename(*, application_key: str, version: str) -> str:
    """安装包规定文件名"""
    return f'{artifact_name_prefix(application_key=application_key)}-{version}-win-x64.exe'


def blockmap_filename(*, application_key: str, version: str) -> str:
    """blockmap 规定文件名"""
    return f'{installer_filename(application_key=application_key, version=version)}.blockmap'


def manifest_filename(*, version: str) -> str:
    """release manifest 保存文件名"""
    return f'release-manifest-{version}.json'


class ReleaseService:
    """版本服务类"""

    @staticmethod
    async def get(*, db: AsyncSession, pk: int) -> Release:
        """获取版本详情"""
        release = await release_dao.get(db, pk)
        if not release:
            raise errors.NotFoundError(msg='版本不存在')
        return release

    @staticmethod
    def _serialize_release_row(row: Any) -> dict[str, Any]:
        """将版本联表结果转换为前端版本详情"""
        release, application_key, application_name, channel_code, channel_name, published_by_name = row
        result = select_columns_serialize(release)
        result.update({
            'application_key': application_key,
            'application_name': application_name,
            'channel_code': channel_code,
            'channel_name': channel_name,
            'published_by_name': published_by_name,
        })
        return result

    @staticmethod
    def _serialize_release_rows(rows: Sequence[Any]) -> list[dict[str, Any]]:
        """批量转换版本联表结果"""
        return [ReleaseService._serialize_release_row(row) for row in rows]

    @staticmethod
    def _read_signature_info(
        release: dict[str, Any], manifest_artifact: dict[str, Any], max_bytes: int
    ) -> dict[str, Any] | None:
        """有界读取已登记 manifest，仅展示摘要和版本身份匹配的白名单声明"""
        try:
            if max_bytes <= 0:
                return None
            path = artifact_storage.resolve_within_root(manifest_artifact['storage_path'])
            with path.open('rb') as stream:
                size = os.fstat(stream.fileno()).st_size
                if size <= 0 or size > max_bytes:
                    return None
                content = stream.read(max_bytes)
                if len(content) != size or os.fstat(stream.fileno()).st_size != size:
                    return None
            if hashlib.sha256(content).hexdigest() != manifest_artifact['sha256']:
                return None
            return ReleaseService._extract_signature_info(release=release, manifest=parse_manifest(content=content))
        except Exception:
            # 历史文件缺失、损坏或存储异常仅降级，不向响应/日志泄漏存储路径。
            return None

    @staticmethod
    def _extract_signature_info(*, release: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any] | None:
        """核对版本身份并提取有限的签名展示字段，不作服务器验签判断"""
        if (
            type(manifest.get('schemaVersion')) is not int
            or manifest['schemaVersion'] != 2
            or manifest.get('version') != release['version']
            or manifest.get('target') != f'{release["platform"]}-{release["arch"]}'
        ):
            return None
        signature = manifest.get('signature')
        if not isinstance(signature, dict):
            return None
        status = signature.get('status')
        if not isinstance(status, str) or status != release['signature_status']:
            return None
        fields = {
            'publisher_name': 'publisherName',
            'installer_thumbprint': 'installerThumbprint',
            'application_thumbprint': 'applicationThumbprint',
            'timestamp_subject': 'timestampSubject',
        }
        info = {}
        for field, source in fields.items():
            value = signature.get(source)
            if value is not None and (not isinstance(value, str) or len(value) > 1024):
                return None
            info[field] = value
        if all(value is None for value in info.values()):
            return None
        return ReleaseSignatureInfo.model_validate(info).model_dump()

    @staticmethod
    async def _attach_signature_info(*, items: list[dict[str, Any]], artifacts: Sequence[Artifact]) -> None:
        """复用已查询产物，一次线程池任务处理整页，线程内不访问 ORM"""
        manifests = {
            artifact.release_id: {'storage_path': artifact.storage_path, 'sha256': artifact.sha256}
            for artifact in artifacts
            if artifact.kind == ArtifactKind.manifest.value
        }
        max_bytes = settings.APP_UPDATE_MAX_MANIFEST_BYTES

        def read_batch() -> list[dict[str, Any] | None]:
            return [
                ReleaseService._read_signature_info(item, manifests[item['id']], max_bytes)
                if item['id'] in manifests
                else None
                for item in items
            ]

        for item, info in zip(items, await asyncio.to_thread(read_batch), strict=True):
            item['signature_info'] = info

    @staticmethod
    async def _get_detail_data(*, db: AsyncSession, pk: int) -> dict[str, Any]:
        """获取包含应用、渠道和发布人信息的版本详情数据"""
        statement = await release_dao.get_detail_select()
        row = (await db.execute(statement.where(Release.id == pk))).first()
        if not row:
            raise errors.NotFoundError(msg='版本不存在')
        return ReleaseService._serialize_release_row(row)

    @staticmethod
    async def get_list(
        *,
        db: AsyncSession,
        application_id: int | None = None,
        channel_id: int | None = None,
        status: str | None = None,
        version: str | None = None,
        published_start: date | None = None,
        published_end: date | None = None,
    ) -> dict[str, Any]:
        """分页获取包含应用、渠道和产物信息的版本列表"""
        if published_start is not None and published_end is not None and published_start > published_end:
            raise errors.RequestError(msg='发布时间开始日期不能晚于结束日期')

        published_start_at = (
            datetime.combine(published_start, time.min, tzinfo=timezone.tz_info)
            if published_start is not None
            else None
        )
        published_end_before = (
            datetime.combine(published_end + timedelta(days=1), time.min, tzinfo=timezone.tz_info)
            if published_end is not None
            else None
        )
        release_select = await release_dao.get_detail_select(
            application_id=application_id,
            channel_id=channel_id,
            status=status,
            version=version,
            published_start_at=published_start_at,
            published_end_before=published_end_before,
        )
        page_data = await paging_data(db, release_select, transformer=ReleaseService._serialize_release_rows)
        items = page_data.get('items', [])
        release_ids = [item['id'] for item in items]
        artifacts_by_release: dict[int, list[dict[str, Any]]] = {release_id: [] for release_id in release_ids}
        artifacts = await artifact_dao.get_by_release_ids(db, release_ids)
        for artifact in artifacts:
            artifacts_by_release[artifact.release_id].append(GetArtifactDetail.model_validate(artifact).model_dump())
        for item in items:
            item['artifacts'] = artifacts_by_release[item['id']]
        await ReleaseService._attach_signature_info(items=items, artifacts=artifacts)
        return page_data

    @staticmethod
    async def get_with_artifacts(*, db: AsyncSession, pk: int) -> GetReleaseWithArtifactDetail:
        """获取包含应用和渠道信息的版本及产物详情"""
        detail_data = await ReleaseService._get_detail_data(db=db, pk=pk)
        artifacts = await artifact_dao.get_by_release(db, pk)
        detail_data['artifacts'] = [GetArtifactDetail.model_validate(artifact) for artifact in artifacts]
        await ReleaseService._attach_signature_info(items=[detail_data], artifacts=artifacts)
        return GetReleaseWithArtifactDetail.model_validate(detail_data)

    @staticmethod
    async def create(*, db: AsyncSession, obj: CreateReleaseParam) -> GetReleaseDetail:
        """创建版本草稿"""
        application = await application_dao.get(db, obj.application_id)
        if not application:
            raise errors.NotFoundError(msg='应用不存在')
        channel = await channel_dao.get(db, obj.channel_id)
        if not channel:
            raise errors.NotFoundError(msg='渠道不存在')
        if channel.application_id != application.id:
            raise errors.RequestError(msg='渠道不属于该应用')
        parse_version(obj.version)
        if await release_dao.get_by_identity(
            db,
            application_id=application.id,
            channel_id=channel.id,
            version=obj.version,
        ):
            raise errors.RequestError(msg='同应用、渠道、版本、平台、架构的版本已存在')
        created = await release_dao.create(db, obj)
        return GetReleaseDetail.model_validate(await ReleaseService._get_detail_data(db=db, pk=created.id))

    @staticmethod
    async def update(*, db: AsyncSession, pk: int, obj: UpdateReleaseParam) -> int:
        """更新版本，仅草稿可编辑"""
        release = await ReleaseService.get(db=db, pk=pk)
        if release.status != ReleaseStatus.draft.value:
            raise errors.RequestError(msg='仅草稿版本允许编辑')
        return await release_dao.update(db, release.id, obj)

    @staticmethod
    async def upload_artifacts(
        *,
        db: AsyncSession,
        pk: int,
        installer: UploadFile,
        blockmap: UploadFile,
        manifest: UploadFile,
    ) -> UploadArtifactResult:
        """
        流式上传并校验三个产物

        顺序：staging 流式写入并复算摘要 -> manifest 对比 -> 原子移动到正式目录 -> 登记数据库
        """
        release = await ReleaseService.get(db=db, pk=pk)
        if release.status != ReleaseStatus.draft.value:
            raise errors.RequestError(msg='仅草稿版本允许上传产物')
        if release.platform != SUPPORTED_PLATFORM or release.arch != SUPPORTED_ARCH:
            raise errors.RequestError(msg='第一版仅支持 win32 x64 版本')

        application = await application_dao.get(db, release.application_id)
        channel = await channel_dao.get(db, release.channel_id)
        if not application or not channel or channel.application_id != application.id:
            raise errors.ServerError(msg='版本关联的应用或渠道数据异常')

        expected_installer = installer_filename(application_key=application.key, version=release.version)
        expected_blockmap = blockmap_filename(application_key=application.key, version=release.version)
        saved_manifest_name = manifest_filename(version=release.version)

        installer_name = safe_filename(filename=installer.filename)
        blockmap_name = safe_filename(filename=blockmap.filename)
        safe_filename(filename=manifest.filename)
        if installer_name != expected_installer:
            raise errors.RequestError(msg=f'安装包文件名必须为 {expected_installer}')
        if blockmap_name != expected_blockmap:
            raise errors.RequestError(msg=f'blockmap 文件名必须为 {expected_blockmap}')

        artifact_storage.ensure_layout()
        staging_dir = artifact_storage.new_staging_dir()
        promoted: list[str] = []
        try:
            staged_installer = await artifact_storage.stream_upload(
                upload_file=installer,
                staging_dir=staging_dir,
                filename=installer_name,
                max_bytes=settings.APP_UPDATE_MAX_INSTALLER_BYTES,
            )
            staged_blockmap = await artifact_storage.stream_upload(
                upload_file=blockmap,
                staging_dir=staging_dir,
                filename=blockmap_name,
                max_bytes=settings.APP_UPDATE_MAX_BLOCKMAP_BYTES,
            )
            staged_manifest = await artifact_storage.stream_upload(
                upload_file=manifest,
                staging_dir=staging_dir,
                filename=saved_manifest_name,
                max_bytes=settings.APP_UPDATE_MAX_MANIFEST_BYTES,
            )

            manifest_data = parse_manifest(content=staged_manifest.path.read_bytes())
            signature_status = validate_release_manifest(
                manifest=manifest_data,
                release_version=release.version,
                installer_filename=installer_name,
                installer_size=staged_installer.size,
                installer_sha256=staged_installer.sha256,
                installer_sha512=staged_installer.sha512,
                blockmap_filename=blockmap_name,
                blockmap_size=staged_blockmap.size,
                blockmap_sha256=staged_blockmap.sha256,
            )

            channel_dir = f'{application.key}/{channel.code}'
            installer_relative = f'{channel_dir}/{installer_name}'
            blockmap_relative = f'{channel_dir}/{blockmap_name}'
            manifest_relative = f'{channel_dir}/{saved_manifest_name}'

            artifact_storage.promote(staged_path=staged_installer.path, final_relative=installer_relative)
            promoted.append(installer_relative)
            artifact_storage.promote(staged_path=staged_blockmap.path, final_relative=blockmap_relative)
            promoted.append(blockmap_relative)
            artifact_storage.promote(staged_path=staged_manifest.path, final_relative=manifest_relative)
            promoted.append(manifest_relative)

            artifacts = [
                Artifact(
                    release_id=release.id,
                    kind=ArtifactKind.installer.value,
                    filename=installer_name,
                    storage_path=installer_relative,
                    size=staged_installer.size,
                    sha256=staged_installer.sha256,
                    sha512=staged_installer.sha512,
                ),
                Artifact(
                    release_id=release.id,
                    kind=ArtifactKind.blockmap.value,
                    filename=blockmap_name,
                    storage_path=blockmap_relative,
                    size=staged_blockmap.size,
                    sha256=staged_blockmap.sha256,
                ),
                Artifact(
                    release_id=release.id,
                    kind=ArtifactKind.manifest.value,
                    filename=saved_manifest_name,
                    storage_path=manifest_relative,
                    size=staged_manifest.size,
                    sha256=staged_manifest.sha256,
                ),
            ]
            await artifact_dao.replace_release_artifacts(db, release.id, artifacts)
            await release_dao.update_signature_status(db, release.id, signature_status)

            fresh_artifacts = await artifact_dao.get_by_release(db, release.id)
            by_kind = {artifact.kind: artifact for artifact in fresh_artifacts}
            return UploadArtifactResult(
                release_id=release.id,
                installer=GetArtifactDetail.model_validate(by_kind[ArtifactKind.installer.value]),
                blockmap=GetArtifactDetail.model_validate(by_kind[ArtifactKind.blockmap.value]),
                manifest=GetArtifactDetail.model_validate(by_kind[ArtifactKind.manifest.value]),
                signature_status=signature_status,
            )
        except Exception:
            for relative in promoted:
                artifact_storage.delete(relative)
            raise
        finally:
            for upload_file in (installer, blockmap, manifest):
                await upload_file.close()
            artifact_storage.cleanup_staging(staging_dir)

    @staticmethod
    def _validate_publish_artifacts(artifacts: Sequence[Artifact]) -> None:
        """检查产物齐全、摘要和磁盘文件，供首次发布和恢复发布复用。"""
        by_kind = {artifact.kind: artifact for artifact in artifacts}
        required = (ArtifactKind.installer.value, ArtifactKind.blockmap.value, ArtifactKind.manifest.value)
        if any(kind not in by_kind for kind in required):
            raise errors.RequestError(msg='installer、blockmap、manifest 三种产物必须齐全')
        if not by_kind[ArtifactKind.installer.value].sha512:
            raise errors.RequestError(msg='安装包缺少 SHA-512 摘要')
        for artifact in (by_kind[kind] for kind in required):
            if not artifact_storage.exists(artifact.storage_path):
                raise errors.RequestError(msg=f'产物文件缺失: {artifact.filename}')

    @staticmethod
    async def publish(*, db: AsyncSession, pk: int, published_by: int) -> PublishReleaseResult:
        """发布版本并切换渠道当前版本"""
        release = await ReleaseService.get(db=db, pk=pk)
        application = await application_dao.get(db, release.application_id)
        channel = await channel_dao.get(db, release.channel_id)
        if not application or not channel or channel.application_id != application.id:
            raise errors.ServerError(msg='版本关联的应用或渠道数据异常')
        if application.status != 'enabled':
            raise errors.RequestError(msg='应用已被禁用，禁止发布')
        if channel.status != 'enabled':
            raise errors.RequestError(msg='渠道已被禁用，禁止发布')
        if release.status not in (ReleaseStatus.draft.value, ReleaseStatus.paused.value):
            raise errors.RequestError(msg='当前状态不允许发布')

        artifacts = await artifact_dao.get_by_release(db, release.id)
        ReleaseService._validate_publish_artifacts(artifacts)

        previous_release_id = channel.current_release_id
        if previous_release_id is not None and previous_release_id != release.id:
            current = await release_dao.get(db, previous_release_id)
            if current and parse_version(release.version) <= parse_version(current.version):
                raise errors.RequestError(msg='新版本号必须高于渠道当前版本')

        await release_dao.mark_published(db, release.id, published_by=published_by)
        await channel_dao.update_current_release(db, channel.id, release.id)
        return PublishReleaseResult(
            release_id=release.id,
            version=release.version,
            status=ReleaseStatus.published.value,
            previous_release_id=previous_release_id,
        )

    @staticmethod
    async def pause(*, db: AsyncSession, pk: int) -> PauseReleaseResult:
        """暂停版本并回退渠道当前版本"""
        release = await ReleaseService.get(db=db, pk=pk)
        if release.status != ReleaseStatus.published.value:
            raise errors.RequestError(msg='仅已发布版本允许暂停')
        channel = await channel_dao.get(db, release.channel_id)
        if not channel:
            raise errors.ServerError(msg='版本关联的渠道数据异常')

        current_release_id = channel.current_release_id
        if current_release_id == release.id:
            fallback = await release_dao.get_latest_published_below(
                db,
                channel_id=release.channel_id,
                version=release.version,
            )
            current_release_id = fallback.id if fallback else None
            await channel_dao.update_current_release(db, channel.id, current_release_id)
        await release_dao.update_status(db, release.id, status=ReleaseStatus.paused.value)
        return PauseReleaseResult(
            release_id=release.id,
            version=release.version,
            status=ReleaseStatus.paused.value,
            fallback_release_id=current_release_id,
        )

    @staticmethod
    async def delete(*, db: AsyncSession, pk: int) -> int:
        """删除非当前的草稿或已暂停版本及其产物文件"""
        release = await ReleaseService.get(db=db, pk=pk)
        if release.status not in (ReleaseStatus.draft.value, ReleaseStatus.paused.value):
            raise errors.RequestError(msg='仅草稿或已暂停版本允许删除')
        channel = await channel_dao.get(db, release.channel_id)
        if channel and channel.current_release_id == release.id:
            raise errors.RequestError(msg='渠道当前版本禁止删除')

        artifacts: Sequence[Artifact] = await artifact_dao.get_by_release(db, release.id)
        for artifact in artifacts:
            artifact_storage.delete(artifact.storage_path)
        await artifact_dao.delete_by_release(db, release.id)
        return await release_dao.delete(db, release.id)

    @staticmethod
    async def _get_user_name(*, db: AsyncSession, user_id: int | None) -> str | None:
        """可空查询 sys_user 名称，用户不存在时返回 None"""
        if user_id is None:
            return None
        result = await db.execute(select(User.nickname).where(User.id == user_id))
        row = result.first()
        return row.name if row else None


release_service: ReleaseService = ReleaseService()
