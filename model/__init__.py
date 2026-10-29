"""app_update 插件模型导入"""

from backend.plugin.app_update.model.application import Application
from backend.plugin.app_update.model.artifact import Artifact
from backend.plugin.app_update.model.channel import Channel
from backend.plugin.app_update.model.release import Release

__all__ = ['Application', 'Artifact', 'Channel', 'Release']
