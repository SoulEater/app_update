"""app_update 插件主路由"""

from fastapi import APIRouter

from backend.core.conf import settings
from backend.plugin.app_update.api.v1.application import router as application_router
from backend.plugin.app_update.api.v1.channel import router as channel_router
from backend.plugin.app_update.api.v1.feed import router as feed_router
from backend.plugin.app_update.api.v1.release import router as release_router

# 管理路由，受 FBA JWT 与 RBAC 保护
v1 = APIRouter(prefix=f'{settings.FASTAPI_API_V1_PATH}/app-updates', tags=['应用管理'])

v1.include_router(application_router, prefix='/applications')
v1.include_router(channel_router, prefix='/channels')
v1.include_router(release_router, prefix='/releases')

# 公开更新源路由，无 JWT，按 IP 宽松限流
feed = APIRouter(prefix='/updates', tags=['应用更新源'])

feed.include_router(feed_router)
