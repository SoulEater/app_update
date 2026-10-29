"""应用管理 API"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from backend.common.pagination import DependsPagination, PageData
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.common.security.permission import RequestPermission
from backend.common.security.rbac import DependsRBAC
from backend.database.db import CurrentSession, CurrentSessionTransaction
from backend.plugin.app_update.schema.application import (
    CreateApplicationParam,
    GetApplicationDetail,
    UpdateApplicationParam,
)
from backend.plugin.app_update.service.application_service import application_service

router = APIRouter()


@router.get(
    '/all',
    summary='获取全部应用',
    dependencies=[DependsJwtAuth],
)
async def get_all_applications(db: CurrentSession) -> ResponseSchemaModel[list[GetApplicationDetail]]:
    """获取全部应用列表"""
    data = await application_service.get_all(db=db)
    return response_base.success(data=data)


@router.get(
    '',
    summary='分页获取应用列表',
    dependencies=[
        DependsJwtAuth,
        DependsPagination,
    ],
)
async def get_applications_paginated(
    db: CurrentSession,
    name: Annotated[str | None, Query(description='应用名称')] = None,
    status: Annotated[str | None, Query(description='状态: enabled/disabled')] = None,
) -> ResponseSchemaModel[PageData[GetApplicationDetail]]:
    """分页获取应用列表"""
    page_data = await application_service.get_list(db=db, name=name, status=status)
    return response_base.success(data=page_data)


@router.get(
    '/{pk}',
    summary='获取应用详情',
    dependencies=[DependsJwtAuth],
)
async def get_application(
    db: CurrentSession,
    pk: Annotated[int, Path(description='应用ID')],
) -> ResponseSchemaModel[GetApplicationDetail]:
    """获取应用详情"""
    data = await application_service.get(db=db, pk=pk)
    return response_base.success(data=data)


@router.post(
    '',
    summary='创建应用',
    dependencies=[
        Depends(RequestPermission('app_update:application:add')),
        DependsRBAC,
    ],
)
async def create_application(db: CurrentSessionTransaction, obj: CreateApplicationParam) -> ResponseModel:
    """创建应用"""
    await application_service.create(db=db, obj=obj)
    return response_base.success()


@router.put(
    '/{pk}',
    summary='更新应用',
    dependencies=[
        Depends(RequestPermission('app_update:application:edit')),
        DependsRBAC,
    ],
)
async def update_application(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='应用ID')],
    obj: UpdateApplicationParam,
) -> ResponseModel:
    """更新应用"""
    await application_service.update(db=db, pk=pk, obj=obj)
    return response_base.success()


@router.delete(
    '/{pk}',
    summary='删除应用',
    dependencies=[
        Depends(RequestPermission('app_update:application:del')),
        DependsRBAC,
    ],
)
async def delete_application(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='应用ID')],
) -> ResponseModel:
    """删除应用，已存在渠道或版本的应用禁止删除"""
    await application_service.delete(db=db, pk=pk)
    return response_base.success()
