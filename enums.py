"""app_update 插件枚举"""

from backend.common.enums import StrEnum


class ApplicationStatus(StrEnum):
    """应用状态"""

    enabled = 'enabled'
    disabled = 'disabled'


class ChannelStatus(StrEnum):
    """渠道状态"""

    enabled = 'enabled'
    disabled = 'disabled'


class ReleaseStatus(StrEnum):
    """版本发布状态"""

    draft = 'draft'
    published = 'published'
    paused = 'paused'


class ArtifactKind(StrEnum):
    """产物类型"""

    installer = 'installer'
    blockmap = 'blockmap'
    manifest = 'manifest'
