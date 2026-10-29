"""版本产物 Schema"""

from pydantic import ConfigDict, Field

from backend.plugin.app_update.schema.base import AppUpdateResponseSchema


class GetArtifactDetail(AppUpdateResponseSchema):
    """产物详情"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description='产物ID')
    release_id: int = Field(description='所属版本ID')
    kind: str = Field(description='产物类型: installer/blockmap/manifest')
    filename: str = Field(description='安全文件名')
    storage_path: str = Field(description='相对存储根目录路径')
    size: int = Field(description='字节数，服务器复算')
    sha256: str = Field(description='小写十六进制 SHA-256，服务器复算')
    sha512: str | None = Field(None, description='Base64 SHA-512，安装包必填')


class UploadArtifactResult(AppUpdateResponseSchema):
    """上传产物结果"""

    release_id: int = Field(description='版本ID')
    installer: GetArtifactDetail = Field(description='安装包产物')
    blockmap: GetArtifactDetail = Field(description='blockmap 产物')
    manifest: GetArtifactDetail = Field(description='release manifest 产物')
    signature_status: str | None = Field(None, description='来自 manifest 的签名状态，仅展示')
