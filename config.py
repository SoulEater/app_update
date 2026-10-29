"""插件独立类型化配置，不要求修改宿主 conf.py。"""

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import rtoml

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from backend.core.path_conf import ENV_FILE_PATH


class AppUpdateSettings(BaseSettings):
    """启动时加载，优先级为进程环境、宿主 .env、插件 TOML；变更后需重启。"""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore',
        hide_input_in_errors=True,
    )

    APP_UPDATE_STORAGE_DIR: str = Field(min_length=1)
    APP_UPDATE_MAX_INSTALLER_BYTES: int = Field(gt=0)
    APP_UPDATE_MAX_BLOCKMAP_BYTES: int = Field(gt=0)
    APP_UPDATE_MAX_MANIFEST_BYTES: int = Field(gt=0, le=16 * 1024 * 1024)
    APP_UPDATE_UPLOAD_CHUNK_BYTES: int = Field(gt=0, le=16 * 1024 * 1024)
    APP_UPDATE_PUBLIC_BASE_URL: str = Field(min_length=1)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """TOML 经初始化参数传入，但其优先级低于显式环境覆盖。"""
        return env_settings, dotenv_settings, init_settings

    @field_validator(
        'APP_UPDATE_MAX_INSTALLER_BYTES',
        'APP_UPDATE_MAX_BLOCKMAP_BYTES',
        'APP_UPDATE_MAX_MANIFEST_BYTES',
        'APP_UPDATE_UPLOAD_CHUNK_BYTES',
        mode='before',
    )
    @classmethod
    def validate_integer(cls, value: Any) -> int:
        """仅接受整数及十进制整数字符串，拒绝布尔、浮点数与空值。"""
        if type(value) is int:
            return value
        if isinstance(value, str) and value.strip().isascii() and value.strip().isdecimal():
            return int(value.strip())
        raise ValueError('必须为正整数')

    @field_validator('APP_UPDATE_STORAGE_DIR')
    @classmethod
    def validate_storage_dir(cls, value: str) -> str:
        """不允许空白路径或 NUL 字符；路径基于宿主 backend/ 解析。"""
        value = value.strip()
        if not value or '\x00' in value:
            raise ValueError('存储目录不能为空或包含 NUL 字符')
        return value

    @field_validator('APP_UPDATE_PUBLIC_BASE_URL')
    @classmethod
    def validate_public_base_url(cls, value: str) -> str:
        """仅接受无认证、查询串和片段的 HTTP(S) 更新源基地址。"""
        value = value.strip().rstrip('/')
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {'http', 'https'}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in value)
            or '\\' in value
        ):
            raise ValueError('更新源基地址必须为无认证信息、查询串和片段的 HTTP(S) URL')
        # 访问 port 属性以拒绝非法端口，不将无效值延迟到客户端请求阶段。
        _ = parsed.port
        return value


def load_app_update_settings() -> AppUpdateSettings:
    """只读取本插件 TOML，并由类型模型完成环境覆盖和启动校验。"""
    config_path = Path(__file__).with_name('plugin.toml')
    config = rtoml.load(config_path)
    return AppUpdateSettings(**config['settings'])


app_update_settings = load_app_update_settings()
