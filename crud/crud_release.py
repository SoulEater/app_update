"""发布版本 CRUD 操作"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.app.admin.model import User
from backend.plugin.app_update.enums import ReleaseStatus
from backend.plugin.app_update.model import Application, Channel, Release
from backend.plugin.app_update.schema.release import CreateReleaseParam, UpdateReleaseParam
from backend.plugin.app_update.utils.version import parse_version
from backend.utils.timezone import timezone


class CRUDRelease(CRUDPlus[Release]):
    """版本 CRUD 类"""

    async def get(self, db: AsyncSession, pk: int) -> Release | None:
        """获取版本"""
        return await self.select_model(db, pk)

    async def get_by_identity(
        self,
        db: AsyncSession,
        *,
        application_id: int,
        channel_id: int,
        version: str,
        platform: str = 'win32',
        arch: str = 'x64',
    ) -> Release | None:
        """通过应用、渠道、版本、平台、架构获取"""
        return await self.select_model_by_column(
            db,
            application_id=application_id,
            channel_id=channel_id,
            version=version,
            platform=platform,
            arch=arch,
        )

    async def get_by_channel(self, db: AsyncSession, channel_id: int) -> Sequence[Release]:
        """获取渠道下全部版本"""
        return await self.select_models(db, channel_id=channel_id)

    async def get_detail_select(
        self,
        *,
        application_id: int | None = None,
        channel_id: int | None = None,
        status: str | None = None,
        version: str | None = None,
        published_start_at: datetime | None = None,
        published_end_before: datetime | None = None,
    ) -> Select:
        """获取包含应用、渠道和发布人信息的版本查询表达式"""
        statement = (
            select(
                Release,
                Application.key.label('application_key'),
                Application.name.label('application_name'),
                Channel.code.label('channel_code'),
                Channel.name.label('channel_name'),
                User.nickname.label('published_by_name'),
            )
            .join(Application, Application.id == Release.application_id)
            .join(Channel, Channel.id == Release.channel_id)
            .outerjoin(User, User.id == Release.published_by)
            .order_by(Release.id.desc())
        )
        if application_id is not None:
            statement = statement.where(Release.application_id == application_id)
        if channel_id is not None:
            statement = statement.where(Release.channel_id == channel_id)
        if status is not None:
            statement = statement.where(Release.status == status)
        if version is not None:
            statement = statement.where(Release.version.ilike(f'%{version}%'))
        if published_start_at is not None:
            statement = statement.where(Release.published_at >= published_start_at)
        if published_end_before is not None:
            statement = statement.where(Release.published_at < published_end_before)
        return statement

    async def get_latest_published_below(self, db: AsyncSession, *, channel_id: int, version: str) -> Release | None:
        """获取同渠道中版本号低于指定版本、状态为 published 的最高版本"""
        bound = parse_version(version)
        releases = await self.select_models(db, channel_id=channel_id, status=ReleaseStatus.published.value)
        candidates = [release for release in releases if parse_version(release.version) < bound]
        if not candidates:
            return None
        return max(candidates, key=lambda release: parse_version(release.version))

    async def create(self, db: AsyncSession, obj: CreateReleaseParam) -> Release:
        """创建版本草稿"""
        data = obj.model_dump()
        data.setdefault('platform', 'win32')
        data.setdefault('arch', 'x64')
        instance = Release(**data)
        db.add(instance)
        await db.flush()
        return instance

    async def update(self, db: AsyncSession, pk: int, obj: UpdateReleaseParam) -> int:
        """更新版本"""
        return await self.update_model(db, pk, obj)

    async def update_status(self, db: AsyncSession, pk: int, *, status: str) -> int:
        """仅更新版本状态"""
        return await self.update_model(db, pk, {'status': status})

    async def update_signature_status(self, db: AsyncSession, pk: int, signature_status: str | None) -> int:
        """更新来自 release manifest 的签名状态"""
        return await self.update_model(db, pk, {'signature_status': signature_status})

    async def mark_published(self, db: AsyncSession, pk: int, *, published_by: int) -> int:
        """置为 published 并记录发布人与发布时间"""
        return await self.update_model(
            db,
            pk,
            {
                'status': ReleaseStatus.published.value,
                'published_by': published_by,
                'published_at': timezone.now(),
            },
        )

    async def delete(self, db: AsyncSession, pk: int) -> int:
        """删除版本"""
        return await self.delete_model(db, pk)


release_dao: CRUDRelease = CRUDRelease(Release)
