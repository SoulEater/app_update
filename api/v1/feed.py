"""公开更新源 API

不使用 JWT，不使用 FBA 统一 JSON 响应包装，直接返回原始 YAML
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from backend.database.db import CurrentSession
from backend.plugin.app_update.service.feed_service import feed_service
from backend.plugin.app_update.utils.limiter import feed_rate_limit

router = APIRouter(dependencies=[Depends(feed_rate_limit())])


@router.get(
    '/{application_key}/{channel_code}/latest.yml',
    summary='获取 latest.yml',
)
async def get_latest_yml(
    db: CurrentSession,
    application_key: Annotated[str, Path(pattern=r'^[a-z0-9][a-z0-9_-]*$', description='应用标识')],
    channel_code: Annotated[str, Path(pattern=r'^[a-z0-9][a-z0-9_-]*$', description='渠道编码')],
) -> Response:
    """兼容 electron-updater generic provider 的动态更新源"""
    content = await feed_service.build_latest_yml(db=db, application_key=application_key, channel_code=channel_code)
    return Response(
        content=content,
        media_type='application/yaml; charset=utf-8',
        headers={
            'Cache-Control': 'no-store, no-cache, must-revalidate',
            'X-Content-Type-Options': 'nosniff',
        },
    )
