"""插件响应 ID 序列化，确保雪花主键及关联外键均无损传给浏览器。"""

from pydantic import field_serializer

from backend.common.schema import SchemaBase
from backend.core.conf import settings


class AppUpdateResponseSchema(SchemaBase):
    """沿用宿主响应约定：自增 ID 返回整数，雪花 ID 返回十进制字符串。"""

    @field_serializer(
        'id',
        'application_id',
        'channel_id',
        'release_id',
        'published_by',
        'current_release_id',
        'previous_release_id',
        'fallback_release_id',
        check_fields=False,
    )
    def serialize_id(self, value: int | None) -> str | int | None:
        """同名覆盖宿主仅处理 id 的 serializer，不将大整数转换为浮点数。"""
        if value is not None and settings.DATABASE_PK_MODE == 'snowflake':
            return str(value)
        return value
