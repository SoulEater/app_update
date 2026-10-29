"""更新渠道管理 API"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from backend.common.pagination import DependsPagination, PageData
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.common.security.permission import RequestPermission
from backend.common.security.rbac import DependsRBAC
from backend.database.db import CurrentSession, CurrentSessionTransaction
from backend.plugin.app_update.schema.channel import (
    CreateChannelParam,
    GetChannelDetail,
    UpdateChannelParam,
)
from backend.plugin.app_update.service.channel_service import channel_service

router = APIRouter()


@router.get(
    '/all',
    summary='获取全部渠道',
    dependencies=[DependsJwtAuth],
)
async def get_all_channels(
    db: CurrentSession,
    application_id: Annotated[int | None, Query(description='按应用ID过滤')] = None,
) -> ResponseSchemaModel[list[GetChannelDetail]]:
    """获取全部渠道列表，可按应用过滤"""
    data = await channel_service.get_all(db=db, application_id=application_id)
    return response_base.success(data=data)


@router.get(
    '',
    summary='分页获取渠道列表',
    dependencies=[
        DependsJwtAuth,
        DependsPagination,
    ],
)
async def get_channels_paginated(
    db: CurrentSession,
    application_id: Annotated[int | None, Query(description='按应用ID过滤')] = None,
    name: Annotated[str | None, Query(description='渠道名称')] = None,
    status: Annotated[str | None, Query(description='状态: enabled/disabled')] = None,
) -> ResponseSchemaModel[PageData[GetChannelDetail]]:
    """分页获取渠道列表"""
    page_data = await channel_service.get_list(db=db, application_id=application_id, name=name, status=status)
    return response_base.success(data=page_data)


@router.get(
    '/{pk}',
    summary='获取渠道详情',
    dependencies=[DependsJwtAuth],
)
async def get_channel(
    db: CurrentSession,
    pk: Annotated[int, Path(description='渠道ID')],
) -> ResponseSchemaModel[GetChannelDetail]:
    """获取渠道详情"""
    data = await channel_service.get_detail(db=db, pk=pk)
    return response_base.success(data=data)


@router.post(
    '',
    summary='创建渠道',
    dependencies=[
        Depends(RequestPermission('app_update:channel:add')),
        DependsRBAC,
    ],
)
async def create_channel(db: CurrentSessionTransaction, obj: CreateChannelParam) -> ResponseModel:
    """创建渠道"""
    await channel_service.create(db=db, obj=obj)
    return response_base.success()


@router.put(
    '/{pk}',
    summary='更新渠道',
    dependencies=[
        Depends(RequestPermission('app_update:channel:edit')),
        DependsRBAC,
    ],
)
async def update_channel(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='渠道ID')],
    obj: UpdateChannelParam,
) -> ResponseModel:
    """更新渠道"""
    await channel_service.update(db=db, pk=pk, obj=obj)
    return response_base.success()


@router.delete(
    '/{pk}',
    summary='删除渠道',
    dependencies=[
        Depends(RequestPermission('app_update:channel:del')),
        DependsRBAC,
    ],
)
async def delete_channel(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='渠道ID')],
) -> ResponseModel:
    """删除渠道，已存在版本或设置了当前版本的渠道禁止删除"""
    await channel_service.delete(db=db, pk=pk)
    return response_base.success()
