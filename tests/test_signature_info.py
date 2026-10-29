"""历史 manifest 签名声明只读响应测试。"""

import hashlib
import json

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.plugin.app_update.schema.release import GetReleaseDetail
from backend.plugin.app_update.service import release_service as rs
from backend.plugin.app_update.tests.test_release_service import make_artifacts, make_release
from backend.plugin.app_update.utils.artifact_storage import ArtifactStorage

# 在收集阶段声明 anyio，避免自动标记 hook 重建参数化测试时丢失 callspec。
pytestmark = pytest.mark.anyio


@pytest.mark.parametrize('status', ['valid', 'signed', 'unsigned-transition', 'unsigned'])
@pytest.mark.parametrize('endpoint', ['list', 'detail'])
async def test_historical_signature_info(tmp_path: Path, status: str, endpoint: str) -> None:
    release = make_release(status='published', signature_status=status)
    data = vars(release) | {
        'application_key': 'demo',
        'application_name': 'Demo',
        'channel_code': 'stable',
        'channel_name': '正式版',
    }
    artifacts = make_artifacts()
    storage = ArtifactStorage(tmp_path)
    path = storage.resolve_within_root(artifacts[-1].storage_path)
    path.parent.mkdir(parents=True)
    signature = {
        'status': status,
        'publisherName': 'Example Publisher',
        'installerThumbprint': 'ABC123',
        'applicationThumbprint': 'DEF456',
        'timestampSubject': 'CN=Timestamp',
        'privateField': 'not exposed',
    }
    content = json.dumps({
        'schemaVersion': 2,
        'version': release.version,
        'target': 'win32-x64',
        'signature': signature,
    }).encode()
    path.write_bytes(content)
    artifacts[-1].sha256 = hashlib.sha256(content).hexdigest()
    before = path.read_bytes()
    with (
        patch.object(rs, 'artifact_storage', storage),
        patch.object(rs, 'artifact_dao') as dao,
        patch.object(rs.ReleaseService, '_get_detail_data', AsyncMock(return_value=data)),
        patch.object(rs, 'release_dao') as release_dao,
        patch.object(rs, 'paging_data', AsyncMock(return_value={'items': [data], 'total': 1})),
    ):
        dao.get_by_release = AsyncMock(return_value=artifacts)
        dao.get_by_release_ids = AsyncMock(return_value=artifacts)
        release_dao.get_detail_select = AsyncMock(return_value=MagicMock())
        db = MagicMock()
        if endpoint == 'list':
            result = (await rs.release_service.get_list(db=db))['items'][0]
            dao.get_by_release_ids.assert_awaited_once_with(db, [release.id])
            dao.get_by_release.assert_not_called()
        else:
            result = (await rs.release_service.get_with_artifacts(db=db, pk=release.id)).model_dump()
        assert result['signature_status'] == status
        assert result['signature_info'] == {
            'publisher_name': 'Example Publisher',
            'installer_thumbprint': 'ABC123',
            'application_thumbprint': 'DEF456',
            'timestamp_subject': 'CN=Timestamp',
        }
        release_dao.update_signature_status.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize('endpoint', ['list', 'detail'])
@pytest.mark.parametrize(
    'failure',
    [
        'no_artifact',
        'missing_file',
        'old_status_only',
        'corrupt',
        'digest',
        'oversize',
        'traversal',
        'absolute',
        'schema',
        'schema_float',
        'version',
        'target',
        'status',
        'signature_type',
        'list',
        'number',
        'boolean',
        'object',
        'too_long',
        'io_error',
    ],
)
async def test_signature_info_failures_degrade(tmp_path: Path, endpoint: str, failure: str) -> None:
    release = make_release(signature_status='valid')
    data = vars(release) | {
        'application_key': 'demo',
        'application_name': 'Demo',
        'channel_code': 'stable',
        'channel_name': '正式版',
    }
    artifacts = make_artifacts()
    artifact = artifacts[-1]
    storage = ArtifactStorage(tmp_path / 'storage')
    path = storage.resolve_within_root(artifact.storage_path)
    path.parent.mkdir(parents=True)
    manifest = {
        'schemaVersion': 2,
        'version': '0.1.2',
        'target': 'win32-x64',
        'signature': {'status': 'valid', 'publisherName': 'Publisher'},
    }
    mutations = {
        'schema': {'schemaVersion': 1},
        'schema_float': {'schemaVersion': 2.0},
        'version': {'version': '9.0.0'},
        'target': {'target': 'darwin-arm64'},
        'old_status_only': {'signature': {'status': 'valid'}},
        'status': {'signature': {'status': 'signed', 'publisherName': 'Publisher'}},
        'signature_type': {'signature': []},
    }
    manifest.update(mutations.get(failure, {}))
    invalid_publishers = {
        'list': [],
        'number': 42,
        'boolean': True,
        'object': {},
        'too_long': 'x' * 1025,
    }
    if failure in invalid_publishers:
        manifest['signature']['publisherName'] = invalid_publishers[failure]
    content = b'not JSON' if failure == 'corrupt' else json.dumps(manifest).encode()
    path.write_bytes(content)
    artifact.sha256 = hashlib.sha256(content).hexdigest()
    if failure == 'no_artifact':
        artifacts = artifacts[:-1]
    elif failure == 'missing_file':
        path.unlink()
    elif failure == 'digest':
        artifact.sha256 = '0' * 64
    elif failure == 'traversal':
        artifact.storage_path = '../outside.json'
    elif failure == 'absolute':
        artifact.storage_path = str(path.resolve())
    max_bytes = len(content) - 1 if failure == 'oversize' else len(content)
    if failure == 'io_error':
        storage.resolve_within_root = MagicMock(side_effect=OSError(str(path)))
    with (
        patch.object(rs, 'artifact_storage', storage),
        patch.object(rs.settings, 'APP_UPDATE_MAX_MANIFEST_BYTES', max_bytes),
        patch.object(rs, 'artifact_dao') as dao,
        patch.object(rs.ReleaseService, '_get_detail_data', AsyncMock(return_value=data)),
        patch.object(rs, 'release_dao') as release_dao,
        patch.object(rs, 'paging_data', AsyncMock(return_value={'items': [data], 'total': 1})),
    ):
        dao.get_by_release = AsyncMock(return_value=artifacts)
        dao.get_by_release_ids = AsyncMock(return_value=artifacts)
        release_dao.get_detail_select = AsyncMock(return_value=MagicMock())
        if endpoint == 'list':
            result = (await rs.release_service.get_list(db=MagicMock()))['items'][0]
        else:
            result = (await rs.release_service.get_with_artifacts(db=MagicMock(), pk=release.id)).model_dump()
    assert result['signature_info'] is None
    assert result['signature_status'] == 'valid'
    assert str(tmp_path) not in json.dumps(result, default=str)


def test_signature_info_schema_default() -> None:
    assert GetReleaseDetail.model_fields['signature_info'].default is None


async def test_signature_info_partial_and_batch(tmp_path: Path) -> None:
    storage = ArtifactStorage(tmp_path)
    items = [vars(make_release(id=i, signature_status='valid')) for i in (10, 11)]
    artifacts = []
    for item in items:
        artifact = make_artifacts(item['id'])[-1]
        artifact.storage_path = f'{item["id"]}.json'
        content = json.dumps({
            'schemaVersion': 2,
            'version': item['version'],
            'target': 'win32-x64',
            'signature': {'status': 'valid', 'publisherName': 'x' * 1024},
        }).encode()
        storage.resolve_within_root(artifact.storage_path).write_bytes(content)
        artifact.sha256 = hashlib.sha256(content).hexdigest()
        artifacts.append(artifact)
    with (
        patch.object(rs, 'artifact_storage', storage),
        patch.object(rs.settings, 'APP_UPDATE_MAX_MANIFEST_BYTES', len(content)),
        patch.object(rs.asyncio, 'to_thread', wraps=rs.asyncio.to_thread) as to_thread,
    ):
        await rs.ReleaseService._attach_signature_info(items=items, artifacts=artifacts)
        to_thread.assert_awaited_once()
    for item in items:
        assert item['signature_info']['publisher_name'] == 'x' * 1024
        assert item['signature_info']['timestamp_subject'] is None
