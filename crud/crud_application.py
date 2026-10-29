"""应用 CRUD 操作"""

from collections.abc import Sequence

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.plugin.app_update.model import Application
from backend.plugin.app_update.schema.application import CreateApplicationParam, UpdateApplicationParam


class CRUDApplication(CRUDPlus[Application]):
    """应用 CRUD 类"""

    async def get(self, db: AsyncSession, pk: int) -> Application | None:
        """获取应用"""
        return await self.select_model(db, pk)

    async def get_by_key(self, db: AsyncSession, key: str) -> Application | None:
        """通过应用标识获取"""
        return await self.select_model_by_column(db, key=key)

    async def get_all(self, db: AsyncSession) -> Sequence[Application]:
        """获取所有应用"""
        return await self.select_models(db)

    async def get_select(
        self,
        *,
        name: str | None = None,
        status: str | None = None,
    ) -> Select:
        """获取应用查询表达式"""
        filters = {}
        if name is not None:
            filters['name__like'] = f'%{name}%'
        if status is not None:
            filters['status'] = status
        return await self.select_order('id', 'desc', **filters)

    async def create(self, db: AsyncSession, obj: CreateApplicationParam) -> Application:
        """创建应用"""
        instance = Application(**obj.model_dump())
        db.add(instance)
        await db.flush()
        return instance

    async def update(self, db: AsyncSession, pk: int, obj: UpdateApplicationParam) -> int:
        """更新应用"""
        return await self.update_model(db, pk, obj)

    async def delete(self, db: AsyncSession, pk: int) -> int:
        """删除应用"""
        return await self.delete_model(db, pk)


application_dao: CRUDApplication = CRUDApplication(Application)
