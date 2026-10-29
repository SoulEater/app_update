"""发布版本管理 API"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Request, UploadFile

from backend.common.pagination import DependsPagination, PageData
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.common.security.permission import RequestPermission
from backend.common.security.rbac import DependsRBAC
from backend.database.db import CurrentSession, CurrentSessionTransaction
from backend.plugin.app_update.schema.artifact import UploadArtifactResult
from backend.plugin.app_update.schema.release import (
    CreateReleaseParam,
    GetReleaseDetail,
    GetReleaseWithArtifactDetail,
    PauseReleaseResult,
    PublishReleaseResult,
    UpdateReleaseParam,
)
from backend.plugin.app_update.service.release_service import release_service

router = APIRouter()


@router.get(
    '',
    summary='分页获取版本列表',
    dependencies=[
        DependsJwtAuth,
        DependsPagination,
    ],
)
async def get_releases_paginated(
    db: CurrentSession,
    application_id: Annotated[int | None, Query(description='按应用ID过滤')] = None,
    channel_id: Annotated[int | None, Query(description='按渠道ID过滤')] = None,
    status: Annotated[str | None, Query(description='状态: draft/published/paused')] = None,
    version: Annotated[str | None, Query(description='版本号模糊过滤')] = None,
    published_start: Annotated[date | None, Query(description='发布时间开始日期（含当天）')] = None,
    published_end: Annotated[date | None, Query(description='发布时间结束日期（含当天）')] = None,
) -> ResponseSchemaModel[PageData[GetReleaseDetail]]:
    """分页获取版本列表，支持应用、渠道、状态、版本和发布时间过滤"""
    page_data = await release_service.get_list(
        db=db,
        application_id=application_id,
        channel_id=channel_id,
        status=status,
        version=version,
        published_start=published_start,
        published_end=published_end,
    )
    return response_base.success(data=page_data)


@router.get(
    '/{pk}',
    summary='获取版本及产物详情',
    dependencies=[DependsJwtAuth],
)
async def get_release(
    db: CurrentSession,
    pk: Annotated[int, Path(description='版本ID')],
) -> ResponseSchemaModel[GetReleaseWithArtifactDetail]:
    """获取版本及产物详情"""
    data = await release_service.get_with_artifacts(db=db, pk=pk)
    return response_base.success(data=data)


@router.post(
    '',
    summary='创建版本草稿',
    dependencies=[
        Depends(RequestPermission('app_update:release:add')),
        DependsRBAC,
    ],
)
async def create_release(
    db: CurrentSessionTransaction,
    obj: CreateReleaseParam,
) -> ResponseSchemaModel[GetReleaseDetail]:
    """创建版本草稿"""
    data = await release_service.create(db=db, obj=obj)
    return response_base.success(data=data)


@router.put(
    '/{pk}',
    summary='更新版本',
    dependencies=[
        Depends(RequestPermission('app_update:release:edit')),
        DependsRBAC,
    ],
)
async def update_release(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='版本ID')],
    obj: UpdateReleaseParam,
) -> ResponseModel:
    """更新版本，仅草稿可编辑"""
    await release_service.update(db=db, pk=pk, obj=obj)
    return response_base.success()


@router.post(
    '/{pk}/artifacts',
    summary='上传并校验版本产物',
    dependencies=[
        Depends(RequestPermission('app_update:release:upload')),
        DependsRBAC,
    ],
)
async def upload_release_artifacts(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='版本ID')],
    file: Annotated[UploadFile, File(description='安装包，文件名必须为 {产物名}-x.y.z-win-x64.exe')],
    blockmap: Annotated[UploadFile, File(description='blockmap，文件名为对应安装包文件名加 .blockmap 后缀')],
    manifest: Annotated[UploadFile, File(description='release manifest JSON')],
) -> ResponseSchemaModel[UploadArtifactResult]:
    """上传 installer、blockmap、manifest 三个产物并完成服务器端校验，产物名为应用 key 首字母大写"""
    data = await release_service.upload_artifacts(db=db, pk=pk, installer=file, blockmap=blockmap, manifest=manifest)
    return response_base.success(data=data)


@router.post(
    '/{pk}/publish',
    summary='发布版本',
    dependencies=[
        Depends(RequestPermission('app_update:release:publish')),
        DependsRBAC,
    ],
)
async def publish_release(
    db: CurrentSessionTransaction,
    request: Request,
    pk: Annotated[int, Path(description='版本ID')],
) -> ResponseSchemaModel[PublishReleaseResult]:
    """发布版本并切换渠道当前版本"""
    data = await release_service.publish(db=db, pk=pk, published_by=request.user.id)
    return response_base.success(data=data)


@router.post(
    '/{pk}/pause',
    summary='暂停版本',
    dependencies=[
        Depends(RequestPermission('app_update:release:pause')),
        DependsRBAC,
    ],
)
async def pause_release(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='版本ID')],
) -> ResponseSchemaModel[PauseReleaseResult]:
    """暂停版本并回指上一个可用版本"""
    data = await release_service.pause(db=db, pk=pk)
    return response_base.success(data=data)


@router.delete(
    '/{pk}',
    summary='删除版本',
    dependencies=[
        Depends(RequestPermission('app_update:release:del')),
        DependsRBAC,
    ],
)
async def delete_release(
    db: CurrentSessionTransaction,
    pk: Annotated[int, Path(description='版本ID')],
) -> ResponseModel:
    """删除非当前的草稿或已暂停版本及其产物文件"""
    await release_service.delete(db=db, pk=pk)
    return response_base.success()
