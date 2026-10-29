"""发布版本 Schema"""

from datetime import datetime

from pydantic import ConfigDict, Field

from backend.common.schema import SchemaBase
from backend.plugin.app_update.schema.artifact import GetArtifactDetail
from backend.plugin.app_update.schema.base import AppUpdateResponseSchema


class CreateReleaseParam(SchemaBase):
    """创建版本参数"""

    application_id: int = Field(description='所属应用ID')
    channel_id: int = Field(description='所属渠道ID')
    version: str = Field(
        max_length=32,
        pattern=r'^\d+\.\d+\.\d+$',
        description='版本号，严格 x.y.z',
    )
    release_notes: str | None = Field(None, description='更新说明')


class UpdateReleaseParam(SchemaBase):
    """更新版本参数"""

    release_notes: str | None = Field(None, description='更新说明')


class ReleaseSignatureInfo(SchemaBase):
    """已存储 manifest 中的签名声明，不代表服务器验签"""

    publisher_name: str | None = Field(None, max_length=1024, description='发布者声明')
    installer_thumbprint: str | None = Field(None, max_length=1024, description='安装包证书指纹声明')
    application_thumbprint: str | None = Field(None, max_length=1024, description='应用证书指纹声明')
    timestamp_subject: str | None = Field(None, max_length=1024, description='时间戳主体声明')


class GetReleaseDetail(AppUpdateResponseSchema):
    """版本详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description='版本ID')
    application_id: int = Field(description='所属应用ID')
    application_key: str = Field(description='应用标识')
    application_name: str = Field(description='应用名称')
    channel_id: int = Field(description='所属渠道ID')
    channel_code: str = Field(description='渠道编码')
    channel_name: str = Field(description='渠道名称')
    version: str = Field(description='版本号')
    platform: str = Field(description='平台')
    arch: str = Field(description='架构')
    release_notes: str | None = Field(None, description='更新说明')
    status: str = Field(description='状态: draft/published/paused')
    signature_status: str | None = Field(None, description='签名状态，仅展示')
    signature_info: ReleaseSignatureInfo | None = Field(None, description='manifest 签名声明，缺失或校验失败为 null')
    published_by: int | None = Field(None, description='发布人ID')
    published_by_name: str | None = Field(None, description='发布人名称，用户不存在时为 null')
    published_at: datetime | None = Field(None, description='发布时间')
    created_time: datetime = Field(description='创建时间')
    updated_time: datetime | None = Field(None, description='更新时间')
    artifacts: list[GetArtifactDetail] = Field(default_factory=list, description='已上传产物列表')


class GetReleaseWithArtifactDetail(GetReleaseDetail):
    """版本及产物详情"""

    artifacts: list[GetArtifactDetail] = Field(default_factory=list, description='产物列表')


class PublishReleaseResult(AppUpdateResponseSchema):
    """发布版本结果"""

    release_id: int = Field(description='版本ID')
    version: str = Field(description='版本号')
    status: str = Field(description='发布后状态')
    previous_release_id: int | None = Field(None, description='发布前渠道当前版本ID')


class PauseReleaseResult(AppUpdateResponseSchema):
    """暂停版本结果"""

    release_id: int = Field(description='版本ID')
    version: str = Field(description='版本号')
    status: str = Field(description='暂停后状态')
    fallback_release_id: int | None = Field(
        None, description='操作后渠道当前版本ID；暂停历史版本时保持原值，无当前版本为 null'
    )
