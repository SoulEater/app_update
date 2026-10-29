"""发布元数据、配置文档及下载白名单的静态合同，不替代真实宿主验收。"""

import re

from pathlib import Path

import pytest
import rtoml

from backend.plugin.app_update.config import AppUpdateSettings
from backend.plugin.validator import validate_plugin_config

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_metadata_and_required_files() -> None:
    config = rtoml.load(ROOT / 'plugin.toml')
    assert validate_plugin_config('app_update', config).value == 'app'
    assert config['plugin']['version'] == '0.2.0'
    for filename in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', '__init__.py'):
        assert (ROOT / filename).is_file()
    assert set(config['settings']) == set(AppUpdateSettings.model_fields)
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    descriptions = readme.split('### 配置项说明', 1)[1].split('大小和分块字段', 1)[0]
    positions = [descriptions.index(f'`{field}`') for field in config['settings']]
    assert positions == sorted(positions)


def test_local_document_links_exist() -> None:
    for source in ROOT.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', source.read_text(encoding='utf-8')):
            if target.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            assert (source.parent / target.split('#', 1)[0]).exists(), (source.relative_to(ROOT), target)


def download_pattern() -> re.Pattern[str]:
    source = (ROOT / 'examples/nginx/app_update.conf').read_text(encoding='utf-8')
    pattern = next(line for line in source.splitlines() if line.startswith('location ~ ^/updates/(?<update_app>'))
    expression = pattern.removeprefix('location ~ ').removesuffix(' {')
    return re.compile(expression.replace('(?<', '(?P<'))


@pytest.mark.parametrize('suffix', ['.exe', '.exe.blockmap'])
def test_nginx_white_list_allows_installer_and_blockmap(suffix: str) -> None:
    assert download_pattern().fullmatch(f'/updates/demo/stable/Demo-1.2.3-win-x64{suffix}')


@pytest.mark.parametrize(
    'path',
    [
        '/updates/.staging/upload-uuid/Demo-1.2.3-win-x64.exe',
        '/updates/demo/stable/release-manifest-1.2.3.json',
        '/updates/demo/stable/../Demo-1.2.3-win-x64.exe',
        '/updates/demo/stable/.hidden.exe',
        '/updates/demo/stable/other.zip',
        '/updates/demo/stable/latest.yml',
        '/updates/demo/stable/Demo-1.2.3-win-x64.exe/extra',
        '/updates/demo/stable/Demo-1.2.3-darwin-arm64.exe',
    ],
)
def test_nginx_white_list_rejects_private_and_unexpected_paths(path: str) -> None:
    assert not download_pattern().fullmatch(path)
