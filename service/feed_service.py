"""公开更新源服务层

按 electron-updater generic provider 合同动态生成 latest.yml，不持久化文件
"""

from datetime import datetime, timezone

import yaml

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exception import errors
from backend.plugin.app_update.crud.crud_application import application_dao
from backend.plugin.app_update.crud.crud_artifact import artifact_dao
from backend.plugin.app_update.crud.crud_channel import channel_dao
from backend.plugin.app_update.crud.crud_release import release_dao
from backend.plugin.app_update.enums import ApplicationStatus, ArtifactKind, ChannelStatus, ReleaseStatus
from backend.plugin.app_update.utils.artifact_storage import artifact_storage


def _format_release_date(value: datetime) -> str:
    """发布时间格式化为 electron-updater 兼容的 UTC ISO 字符串"""
    moment = value.astimezone(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + f'{moment.microsecond // 1000:03d}Z'


def build_feed_document(
    *,
    version: str,
    filename: str,
    sha512: str,
    size: int,
    release_date: str,
    release_notes: str | None = None,
) -> dict:
    """构建 electron-updater generic provider 兼容的 latest.yml 文档对象"""
    document = {
        'version': version,
        'files': [
            {
                'url': filename,
                'sha512': sha512,
                'size': size,
            }
        ],
        'path': filename,
        'sha512': sha512,
        'releaseDate': release_date,
    }
    if release_notes:
        document['releaseNotes'] = release_notes
    return document


def dump_feed_yml(document: dict) -> str:
    """安全序列化 latest.yml，由 yaml 库负责转义"""
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=4096,
    )


class FeedService:
    """公开更新源服务类"""

    @staticmethod
    async def build_latest_yml(*, db: AsyncSession, application_key: str, channel_code: str) -> str:
        """
        构建指定应用与渠道的 latest.yml 内容

        任一环节不满足时返回 404，避免向客户端暴露不可用更新源
        """
        application = await application_dao.get_by_key(db, application_key)
        if not application or application.status != ApplicationStatus.enabled.value:
            raise errors.NotFoundError(msg='更新源不存在')
        channel = await channel_dao.get_by_code(db, application.id, channel_code)
        if not channel or channel.status != ChannelStatus.enabled.value:
            raise errors.NotFoundError(msg='更新源不存在')
        if channel.current_release_id is None:
            raise errors.NotFoundError(msg='更新源不存在')

        release = await release_dao.get(db, channel.current_release_id)
        if not release or release.status != ReleaseStatus.published.value:
            raise errors.NotFoundError(msg='更新源不存在')

        artifacts = await artifact_dao.get_by_release(db, release.id)
        by_kind = {artifact.kind: artifact for artifact in artifacts}
        installer = by_kind.get(ArtifactKind.installer.value)
        blockmap = by_kind.get(ArtifactKind.blockmap.value)
        if not installer or not blockmap or not installer.sha512:
            raise errors.NotFoundError(msg='更新源不存在')
        if not artifact_storage.exists(installer.storage_path) or not artifact_storage.exists(blockmap.storage_path):
            raise errors.NotFoundError(msg='更新源不存在')

        release_date = (
            _format_release_date(release.published_at)
            if release.published_at
            else _format_release_date(release.created_time)
        )
        document = build_feed_document(
            version=release.version,
            filename=installer.filename,
            sha512=installer.sha512,
            size=installer.size,
            release_date=release_date,
            release_notes=release.release_notes,
        )
        return dump_feed_yml(document)


feed_service: FeedService = FeedService()
