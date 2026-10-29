"""应用 Schema"""

from datetime import datetime

from pydantic import ConfigDict, Field

from backend.common.schema import SchemaBase
from backend.plugin.app_update.schema.base import AppUpdateResponseSchema


class ApplicationSchemaBase(SchemaBase):
    """应用基础 Schema"""

    name: str = Field(max_length=128, description='应用名称')
    description: str | None = Field(None, description='应用说明')


class CreateApplicationParam(SchemaBase):
    """创建应用参数"""

    key: str = Field(
        pattern=r'^[a-z0-9][a-z0-9_-]{1,63}$',
        description='应用标识，小写字母、数字、下划线和连字符，创建后禁止修改',
    )
    name: str = Field(max_length=128, description='应用名称')
    description: str | None = Field(None, description='应用说明')


class UpdateApplicationParam(SchemaBase):
    """更新应用参数"""

    name: str = Field(None, max_length=128, description='应用名称')
    description: str | None = Field(None, description='应用说明')
    status: str | None = Field(None, description='状态: enabled/disabled')


class GetApplicationDetail(AppUpdateResponseSchema, ApplicationSchemaBase):
    """应用详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description='应用ID')
    key: str = Field(description='应用标识')
    status: str = Field(description='状态: enabled/disabled')
    created_time: datetime = Field(description='创建时间')
    updated_time: datetime | None = Field(None, description='更新时间')
