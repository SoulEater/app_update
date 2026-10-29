"""应用服务层"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exception import errors
from backend.common.pagination import paging_data
from backend.plugin.app_update.crud.crud_application import application_dao
from backend.plugin.app_update.crud.crud_channel import channel_dao
from backend.plugin.app_update.crud.crud_release import release_dao
from backend.plugin.app_update.model import Application
from backend.plugin.app_update.schema.application import CreateApplicationParam, UpdateApplicationParam


class ApplicationService:
    """应用服务类"""

    @staticmethod
    async def get(*, db: AsyncSession, pk: int) -> Application:
        """获取应用详情"""
        application = await application_dao.get(db, pk)
        if not application:
            raise errors.NotFoundError(msg='应用不存在')
        return application

    @staticmethod
    async def get_list(*, db: AsyncSession, name: str | None = None, status: str | None = None) -> dict[str, Any]:
        """分页获取应用列表"""
        application_select = await application_dao.get_select(name=name, status=status)
        return await paging_data(db, application_select)

    @staticmethod
    async def get_all(*, db: AsyncSession) -> Sequence[Application]:
        """获取全部应用"""
        return await application_dao.get_all(db)

    @staticmethod
    async def create(*, db: AsyncSession, obj: CreateApplicationParam) -> Application:
        """创建应用，应用标识唯一"""
        if await application_dao.get_by_key(db, obj.key):
            raise errors.RequestError(msg=f'应用标识 {obj.key} 已存在')
        return await application_dao.create(db, obj)

    @staticmethod
    async def update(*, db: AsyncSession, pk: int, obj: UpdateApplicationParam) -> int:
        """更新应用，应用标识禁止修改"""
        application = await ApplicationService.get(db=db, pk=pk)
        if obj.status is not None and obj.status not in ('enabled', 'disabled'):
            raise errors.RequestError(msg='状态仅允许 enabled 或 disabled')
        return await application_dao.update(db, application.id, obj)

    @staticmethod
    async def delete(*, db: AsyncSession, pk: int) -> int:
        """删除应用，已存在渠道或版本时禁止删除"""
        application = await ApplicationService.get(db=db, pk=pk)
        if await channel_dao.count(db, application_id=application.id):
            raise errors.RequestError(msg='应用下已存在渠道，禁止删除')
        if await release_dao.count(db, application_id=application.id):
            raise errors.RequestError(msg='应用下已存在版本，禁止删除')
        return await application_dao.delete(db, application.id)


application_service: ApplicationService = ApplicationService()
