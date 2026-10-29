"""更新渠道 Schema"""

from datetime import datetime

from pydantic import ConfigDict, Field

from backend.common.schema import SchemaBase
from backend.plugin.app_update.schema.base import AppUpdateResponseSchema


class ChannelSchemaBase(SchemaBase):
    """渠道基础 Schema"""

    name: str = Field(max_length=64, description='渠道名称')


class CreateChannelParam(SchemaBase):
    """创建渠道参数"""

    application_id: int = Field(description='所属应用ID')
    code: str = Field(
        pattern=r'^[a-z0-9][a-z0-9_-]{1,31}$',
        description='渠道编码，小写字母、数字、下划线和连字符，创建后禁止修改',
    )
    name: str = Field(max_length=64, description='渠道名称')


class UpdateChannelParam(SchemaBase):
    """更新渠道参数"""

    name: str | None = Field(None, max_length=64, description='渠道名称')
    status: str | None = Field(None, description='状态: enabled/disabled')


class GetChannelDetail(AppUpdateResponseSchema, ChannelSchemaBase):
    """渠道详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description='渠道ID')
    application_id: int = Field(description='所属应用ID')
    application_name: str = Field(description='所属应用名称')
    code: str = Field(description='渠道编码')
    status: str = Field(description='状态: enabled/disabled')
    current_release_id: int | None = Field(None, description='客户端当前可见版本ID')
    current_version: str | None = Field(None, description='当前版本号')
    feed_url: str = Field(description='更新源地址')
    created_time: datetime = Field(description='创建时间')
    updated_time: datetime | None = Field(None, description='更新时间')
