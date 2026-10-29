"""更新渠道 CRUD 操作"""

from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.plugin.app_update.model import Application, Channel, Release
from backend.plugin.app_update.schema.channel import CreateChannelParam, UpdateChannelParam


class CRUDChannel(CRUDPlus[Channel]):
    """渠道 CRUD 类"""

    async def get(self, db: AsyncSession, pk: int) -> Channel | None:
        """获取渠道"""
        return await self.select_model(db, pk)

    async def get_by_code(self, db: AsyncSession, application_id: int, code: str) -> Channel | None:
        """通过应用与渠道编码获取"""
        return await self.select_model_by_column(db, application_id=application_id, code=code)

    async def get_all(self, db: AsyncSession, *, application_id: int | None = None) -> Sequence[Channel]:
        """获取渠道列表，可按应用过滤"""
        filters = {}
        if application_id is not None:
            filters['application_id'] = application_id
        return await self.select_models(db, **filters)

    async def get_detail_select(
        self,
        *,
        application_id: int | None = None,
        name: str | None = None,
    ) -> Select:
        """获取包含应用和当前版本信息的渠道查询表达式"""
        statement = (
            select(
                Channel,
                Application.name.label('application_name'),
                Application.key.label('application_key'),
                Release.version.label('current_version'),
            )
            .join(Application, Application.id == Channel.application_id)
            .outerjoin(Release, Release.id == Channel.current_release_id)
            .order_by(Channel.id.desc())
        )
        if application_id is not None:
            statement = statement.where(Channel.application_id == application_id)
        if name is not None:
            statement = statement.where(Channel.name.ilike(f'%{name}%'))
        return statement

    async def get_select(
        self,
        *,
        application_id: int | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> Select:
        """获取渠道查询表达式"""
        statement = await self.get_detail_select(application_id=application_id, name=name)
        if status is not None:
            statement = statement.where(Channel.status == status)
        return statement

    async def create(self, db: AsyncSession, obj: CreateChannelParam) -> Channel:
        """创建渠道"""
        instance = Channel(**obj.model_dump())
        db.add(instance)
        await db.flush()
        return instance

    async def update(self, db: AsyncSession, pk: int, obj: UpdateChannelParam) -> int:
        """更新渠道"""
        return await self.update_model(db, pk, obj)

    async def update_current_release(self, db: AsyncSession, pk: int, release_id: int | None) -> int:
        """更新渠道当前版本指向"""
        return await self.update_model(db, pk, {'current_release_id': release_id})

    async def delete(self, db: AsyncSession, pk: int) -> int:
        """删除渠道"""
        return await self.delete_model(db, pk)


channel_dao: CRUDChannel = CRUDChannel(Channel)
