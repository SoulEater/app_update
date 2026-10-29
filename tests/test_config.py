"""独立配置优先级、类型和无宿主补丁回归测试。"""

from pathlib import Path

import pytest
import rtoml

from pydantic import ValidationError

from backend.plugin.app_update.config import AppUpdateSettings

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = rtoml.load(PLUGIN_ROOT / 'plugin.toml')['settings']


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in DEFAULTS:
        monkeypatch.delenv(key, raising=False)


def test_toml_defaults_without_host_settings_fields() -> None:
    settings = AppUpdateSettings(_env_file=None, **DEFAULTS)
    assert settings.model_dump() == DEFAULTS
    assert settings.APP_UPDATE_MAX_MANIFEST_BYTES == 1024 * 1024


def test_environment_overrides_dotenv_and_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / '.env'
    env_file.write_text(
        "APP_UPDATE_PUBLIC_BASE_URL='https://dotenv.example/updates'\n"
        'APP_UPDATE_MAX_INSTALLER_BYTES=4096\n'
        'UNRELATED_HOST_SECRET=ignored\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('APP_UPDATE_PUBLIC_BASE_URL', 'https://environment.example/updates/')
    monkeypatch.setenv('APP_UPDATE_UPLOAD_CHUNK_BYTES', '128')
    settings = AppUpdateSettings(_env_file=env_file, **DEFAULTS)
    assert settings.APP_UPDATE_PUBLIC_BASE_URL == 'https://environment.example/updates'
    assert settings.APP_UPDATE_MAX_INSTALLER_BYTES == 4096
    assert settings.APP_UPDATE_UPLOAD_CHUNK_BYTES == 128
    assert not hasattr(settings, 'UNRELATED_HOST_SECRET')


@pytest.mark.parametrize('field', [key for key in DEFAULTS if key.endswith('_BYTES')])
def test_numeric_dotenv_values_are_integers(tmp_path: Path, field: str) -> None:
    env_file = tmp_path / '.env'
    env_file.write_text(f'{field}=1024\n', encoding='utf-8')
    settings = AppUpdateSettings(_env_file=env_file, **DEFAULTS)
    assert getattr(settings, field) == 1024
    assert type(getattr(settings, field)) is int


@pytest.mark.parametrize('value', ['0', '-1', '', '1.5', 'true', True, 1.5, None, '１２８'])
@pytest.mark.parametrize('field', [key for key in DEFAULTS if key.endswith('_BYTES')])
def test_reject_invalid_numeric_config(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        AppUpdateSettings(_env_file=None, **(DEFAULTS | {field: value}))


@pytest.mark.parametrize('field', ['APP_UPDATE_MAX_MANIFEST_BYTES', 'APP_UPDATE_UPLOAD_CHUNK_BYTES'])
def test_reject_unbounded_memory_config(field: str) -> None:
    with pytest.raises(ValidationError):
        AppUpdateSettings(_env_file=None, **(DEFAULTS | {field: 16 * 1024 * 1024 + 1}))


@pytest.mark.parametrize(
    'url',
    [
        '',
        'relative/updates',
        'ftp://example.com/updates',
        'https://example.com/updates?token=secret',
        'https://example.com/updates#fragment',
        'https://user:secret@example.com/updates',
        'https://example.com:invalid/updates',
        'https://example.com:65536/updates',
        'https://exam ple.com/updates',
        'https://example.com\\evil/updates',
    ],
)
def test_reject_invalid_public_url_without_leaking_values(url: str) -> None:
    with pytest.raises(ValidationError) as captured:
        AppUpdateSettings(_env_file=None, **(DEFAULTS | {'APP_UPDATE_PUBLIC_BASE_URL': url}))
    assert 'input_value=' not in str(captured.value)
    assert 'user:secret' not in str(captured.value)


@pytest.mark.parametrize('url', ['http://localhost:8000/updates', 'https://example.com/downloads/updates'])
def test_accept_local_and_reverse_proxy_base_urls(url: str) -> None:
    settings = AppUpdateSettings(_env_file=None, **(DEFAULTS | {'APP_UPDATE_PUBLIC_BASE_URL': url}))
    assert url == settings.APP_UPDATE_PUBLIC_BASE_URL


@pytest.mark.parametrize('value', ['', '   ', 'bad\x00path'])
def test_reject_invalid_storage_path(value: str) -> None:
    with pytest.raises(ValidationError):
        AppUpdateSettings(_env_file=None, **(DEFAULTS | {'APP_UPDATE_STORAGE_DIR': value}))
