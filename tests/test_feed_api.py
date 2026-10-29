"""公开更新源测试；集成测试仅用于专用测试库，默认不启用。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid

from datetime import datetime
from typing import TYPE_CHECKING, TypedDict
from zoneinfo import ZoneInfo

import pytest
import yaml

from backend.core.conf import settings
from backend.plugin.app_update.service.feed_service import (
    _format_release_date,
    build_feed_document,
    dump_feed_yml,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from starlette.testclient import TestClient


class IntegrationApplication(TypedDict):
    id: int
    key: str
    channel_id: int
    base: str


TZ = ZoneInfo('Asia/Shanghai')

NOTES_CASES = [
    '普通更新说明',
    '包含冒号: 与空格 的说明',
    '包含单引号\' 和双引号" 的说明',
    '第一行\n第二行\n\n第四行',
    '特殊字符 # 注释样式\n- 列表样式\n  缩进内容',
    'Unicode: 中文、にほんご、한국어、🌍🎉',
    '- [ ] 复选框\n- [x] 已完成',
    'YAML 控制字符 --- 与 ... 结尾',
]


def test_format_release_date_utc() -> None:
    value = datetime(2026, 8, 25, 17, 35, 47, 778000, tzinfo=TZ)
    assert _format_release_date(value) == '2026-08-25T09:35:47.778Z'


def test_format_release_date_pattern() -> None:
    value = datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=TZ)
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z', _format_release_date(value))


def test_build_feed_document_with_notes() -> None:
    document = build_feed_document(
        version='0.1.2',
        filename='Myapp-0.1.2-win-x64.exe',
        sha512='abc',
        size=100,
        release_date='2026-08-25T09:35:47.778Z',
        release_notes='说明',
    )
    assert document['version'] == '0.1.2'
    assert document['path'] == 'Myapp-0.1.2-win-x64.exe'
    assert document['files'][0]['url'] == 'Myapp-0.1.2-win-x64.exe'
    assert document['releaseNotes'] == '说明'


def test_build_feed_document_without_notes() -> None:
    document = build_feed_document(
        version='0.1.2',
        filename='Myapp-0.1.2-win-x64.exe',
        sha512='abc',
        size=100,
        release_date='2026-08-25T09:35:47.778Z',
    )
    assert 'releaseNotes' not in document


@pytest.mark.parametrize('notes', NOTES_CASES)
def test_dump_feed_yml_round_trip_special_characters(notes: str) -> None:
    document = build_feed_document(
        version='0.1.2',
        filename='Myapp-0.1.2-win-x64.exe',
        sha512='sha512-value',
        size=182907511,
        release_date='2026-08-25T09:35:47.778Z',
        release_notes=notes,
    )
    dumped = dump_feed_yml(document)
    assert yaml.safe_load(dumped) == document


def test_dump_feed_yml_injection_is_neutralized() -> None:
    document = build_feed_document(
        version='0.1.2',
        filename='Myapp-0.1.2-win-x64.exe',
        sha512='sha512-value',
        size=1,
        release_date='2026-08-25T09:35:47.778Z',
        release_notes='version: 9.9.9\nfiles: []',
    )
    loaded = yaml.safe_load(dump_feed_yml(document))
    assert loaded['version'] == '0.1.2'
    assert loaded['releaseNotes'] == 'version: 9.9.9\nfiles: []'


@pytest.fixture
def integration_application(
    client: TestClient, token_headers: dict[str, str]
) -> Generator[IntegrationApplication, None, None]:
    """隔离应用与渠道，测试不改变 demo 或任何既有渠道指针。"""
    base = f'{settings.FASTAPI_API_V1_PATH}/app-updates'
    key = f'test_{uuid.uuid4().hex[:12]}'
    created = client.post(
        f'{base}/applications',
        headers=token_headers,
        json={'key': key, 'name': 'Integration Test', 'status': 'enabled'},
    )
    assert created.status_code == 200, created.text
    # 创建应用/渠道接口仅返回成功状态，ID 应从公开查询接口获取。
    applications = client.get(f'{base}/applications/all', headers=token_headers)
    assert applications.status_code == 200, applications.text
    application_id = next(row['id'] for row in applications.json()['data'] if row['key'] == key)
    channel_id = None
    try:
        channel = client.post(
            f'{base}/channels',
            headers=token_headers,
            json={'application_id': application_id, 'code': 'stable', 'name': 'Test Stable', 'status': 'enabled'},
        )
        assert channel.status_code == 200, channel.text
        channels = client.get(f'{base}/channels/all', headers=token_headers, params={'application_id': application_id})
        assert channels.status_code == 200, channels.text
        channel_id = next(row['id'] for row in channels.json()['data'] if row['code'] == 'stable')
        yield {'id': application_id, 'key': key, 'channel_id': channel_id, 'base': base}
    finally:
        if channel_id is not None:
            client.delete(f'{base}/channels/{channel_id}', headers=token_headers)
        client.delete(f'{base}/applications/{application_id}', headers=token_headers)


def build_integration_payloads(application_key: str, version: str) -> dict[str, tuple[str, bytes, str]]:
    """仅创建协议测试字节，不伪造可安装 NSIS 或已验签产物。"""
    prefix = application_key[:1].upper() + application_key[1:]
    filename = f'{prefix}-{version}-win-x64.exe'
    installer = b'e2e-installer-' + version.encode()
    blockmap = b'e2e-blockmap-' + version.encode()
    manifest = {
        'schemaVersion': 2,
        'version': version,
        'target': 'win32-x64',
        'artifact': {
            'filename': filename,
            'bytes': len(installer),
            'sha256': hashlib.sha256(installer).hexdigest(),
            'sha512': base64.b64encode(hashlib.sha512(installer).digest()).decode('ascii'),
        },
        'blockmap': {
            'filename': f'{filename}.blockmap',
            'bytes': len(blockmap),
            'sha256': hashlib.sha256(blockmap).hexdigest(),
        },
        'signature': {'status': 'unknown'},
    }
    return {
        'file': (filename, installer, 'application/octet-stream'),
        'blockmap': (f'{filename}.blockmap', blockmap, 'application/octet-stream'),
        'manifest': ('release-manifest.json', json.dumps(manifest).encode('utf-8'), 'application/json'),
    }


def test_integration_payloads_use_selected_application_key() -> None:
    payload = build_integration_payloads('test_app', '0.1.0')
    manifest = json.loads(payload['manifest'][1])
    assert payload['file'][0] == 'Test_app-0.1.0-win-x64.exe'
    assert manifest['artifact']['filename'] == payload['file'][0]
    assert manifest['signature']['status'] == 'unknown'


def cleanup_integration_releases(
    client: TestClient, token_headers: dict[str, str], base: str, release_ids: list[int]
) -> None:
    """Pause published releases before deleting the isolated test data."""
    for release_id in reversed(release_ids):
        detail = client.get(f'{base}/releases/{release_id}', headers=token_headers)
        if detail.status_code == 200 and detail.json()['data']['status'] == 'published':
            client.post(f'{base}/releases/{release_id}/pause', headers=token_headers)
        client.delete(f'{base}/releases/{release_id}', headers=token_headers)


@pytest.mark.skipif(
    os.environ.get('FBA_INTEGRATION', '').lower() not in ('1', 'true', 'yes'),
    reason='仅专用测试库可设置 FBA_INTEGRATION=1，需要数据库、Redis 及测试管理员',
)
class TestFeedApiIntegration:
    """通过真实鉴权与数据库验证更新源。"""

    def test_latest_yml_requires_no_auth(self, client: TestClient) -> None:
        response = client.get('/updates/does-not-exist/stable/latest.yml')
        assert response.status_code == 404

    def test_empty_channel_has_no_feed(
        self, client: TestClient, integration_application: IntegrationApplication
    ) -> None:
        key = integration_application['key']
        assert client.get(f'/updates/{key}/stable/latest.yml').status_code == 404

    def test_admin_applications_requires_auth(self, client: TestClient) -> None:
        response = client.get(f'{settings.FASTAPI_API_V1_PATH}/app-updates/applications/all')
        assert response.status_code == 401

    def test_admin_applications_with_token(
        self, client: TestClient, token_headers: dict[str, str], integration_application: IntegrationApplication
    ) -> None:
        response = client.get(f'{integration_application["base"]}/applications/all', headers=token_headers)
        assert response.status_code == 200, response.text
        assert integration_application['key'] in {item['key'] for item in response.json()['data']}

    def test_release_lifecycle_and_fallback(
        self, client: TestClient, token_headers: dict[str, str], integration_application: IntegrationApplication
    ) -> None:
        app = integration_application
        base = app['base']
        feed_url = f'/updates/{app["key"]}/stable/latest.yml'
        release_ids: list[int] = []
        try:
            for version in ('0.1.0', '0.2.0'):
                created = client.post(
                    f'{base}/releases',
                    headers=token_headers,
                    json={
                        'application_id': app['id'],
                        'channel_id': app['channel_id'],
                        'version': version,
                        'release_notes': 'e2e\n发布: 测试',
                    },
                )
                assert created.status_code == 200, created.text
                release_id = created.json()['data']['id']
                release_ids.append(release_id)
                uploaded = client.post(
                    f'{base}/releases/{release_id}/artifacts',
                    headers=token_headers,
                    files=build_integration_payloads(app['key'], version),
                )
                assert uploaded.status_code == 200, uploaded.text
                assert uploaded.json()['data']['installer']['size'] > 0
                published = client.post(f'{base}/releases/{release_id}/publish', headers=token_headers)
                assert published.status_code == 200, published.text
                feed = client.get(feed_url)
                assert feed.status_code == 200, feed.text
                assert feed.headers['content-type'].startswith('application/yaml')
                assert feed.headers['cache-control'] == 'no-store, no-cache, must-revalidate'
                payload = yaml.safe_load(feed.text)
                assert payload['version'] == version
                assert payload['path'] == build_integration_payloads(app['key'], version)['file'][0]
                assert payload['files'][0]['url'] == payload['path']

            paused = client.post(f'{base}/releases/{release_ids[-1]}/pause', headers=token_headers)
            assert paused.status_code == 200, paused.text
            assert paused.json()['data']['fallback_release_id'] == release_ids[0]
            assert yaml.safe_load(client.get(feed_url).text)['version'] == '0.1.0'
            paused = client.post(f'{base}/releases/{release_ids[0]}/pause', headers=token_headers)
            assert paused.status_code == 200, paused.text
            assert paused.json()['data']['fallback_release_id'] is None
            assert client.get(feed_url).status_code == 404
        finally:
            cleanup_integration_releases(client, token_headers, base, release_ids)
