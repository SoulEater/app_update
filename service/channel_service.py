"""更新渠道服务层"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exception import errors
from backend.common.pagination import paging_data
from backend.plugin.app_update.config import app_update_settings as settings
from backend.plugin.app_update.crud.crud_channel import channel_dao
from backend.plugin.app_update.crud.crud_release import release_dao
from backend.plugin.app_update.model import Channel
from backend.plugin.app_update.schema.channel import CreateChannelParam, UpdateChannelParam
from backend.plugin.app_update.service.application_service import application_service
from backend.utils.serializers import select_columns_serialize


class ChannelService:
    """渠道服务类"""

    @staticmethod
    async def get(*, db: AsyncSession, pk: int) -> Channel:
        """获取渠道详情"""
        channel = await channel_dao.get(db, pk)
        if not channel:
            raise errors.NotFoundError(msg='渠道不存在')
        return channel

    @staticmethod
    def _serialize_channel_row(row: Any) -> dict[str, Any]:
        """将渠道联表结果转换为前端渠道详情"""
        channel, application_name, application_key, current_version = row
        result = select_columns_serialize(channel)
        result.update({
            'application_name': application_name,
            'current_version': current_version,
            'feed_url': (f'{settings.APP_UPDATE_PUBLIC_BASE_URL.rstrip("/")}/{application_key}/{channel.code}/'),
        })
        return result

    @staticmethod
    async def get_detail(*, db: AsyncSession, pk: int) -> dict[str, Any]:
        """获取包含所属应用信息的渠道详情"""
        statement = await channel_dao.get_detail_select()
        row = (await db.execute(statement.where(Channel.id == pk))).first()
        if not row:
            raise errors.NotFoundError(msg='渠道不存在')
        return ChannelService._serialize_channel_row(row)

    @staticmethod
    async def get_list(
        *,
        db: AsyncSession,
        application_id: int | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """分页获取包含所属应用信息的渠道列表"""
        channel_select = await channel_dao.get_select(application_id=application_id, name=name, status=status)
        return await paging_data(db, channel_select, transformer=ChannelService._serialize_channel_rows)

    @staticmethod
    def _serialize_channel_rows(rows: Sequence[Any]) -> list[dict[str, Any]]:
        """批量转换渠道联表结果"""
        return [ChannelService._serialize_channel_row(row) for row in rows]

    @staticmethod
    async def get_all(*, db: AsyncSession, application_id: int | None = None) -> list[dict[str, Any]]:
        """获取包含所属应用信息的全部渠道"""
        statement = await channel_dao.get_detail_select(application_id=application_id)
        rows = (await db.execute(statement)).all()
        return [ChannelService._serialize_channel_row(row) for row in rows]

    @staticmethod
    async def create(*, db: AsyncSession, obj: CreateChannelParam) -> Channel:
        """创建渠道，同一应用下渠道编码唯一"""
        application = await application_service.get(db=db, pk=obj.application_id)
        if await channel_dao.get_by_code(db, application.id, obj.code):
            raise errors.RequestError(msg=f'应用下已存在渠道编码 {obj.code}')
        return await channel_dao.create(db, obj)

    @staticmethod
    async def update(*, db: AsyncSession, pk: int, obj: UpdateChannelParam) -> int:
        """更新渠道，渠道编码禁止修改"""
        channel = await ChannelService.get(db=db, pk=pk)
        if obj.status is not None and obj.status not in ('enabled', 'disabled'):
            raise errors.RequestError(msg='状态仅允许 enabled 或 disabled')
        return await channel_dao.update(db, channel.id, obj)

    @staticmethod
    async def delete(*, db: AsyncSession, pk: int) -> int:
        """删除渠道，已存在版本或设置了当前版本时禁止删除"""
        channel = await ChannelService.get(db=db, pk=pk)
        if channel.current_release_id is not None:
            raise errors.RequestError(msg='渠道已设置当前版本，禁止删除')
        if await release_dao.count(db, channel_id=channel.id):
            raise errors.RequestError(msg='渠道下已存在版本，禁止删除')
        return await channel_dao.delete(db, channel.id)


channel_service: ChannelService = ChannelService()
