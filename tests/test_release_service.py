"""发布版本服务状态机单元测试（mock DAO 与存储层）"""

import base64
import hashlib
import io
import json

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from anyio import to_thread
from fastapi import UploadFile

from backend.common.exception import errors
from backend.plugin.app_update.service import release_service as rs
from backend.plugin.app_update.utils.artifact_storage import ArtifactStorage

TZ = ZoneInfo('Asia/Shanghai')


def make_release(**overrides: Any) -> SimpleNamespace:
    base = {
        'id': 10,
        'application_id': 1,
        'channel_id': 2,
        'version': '0.1.2',
        'platform': 'win32',
        'arch': 'x64',
        'release_notes': None,
        'status': 'draft',
        'signature_status': None,
        'published_by': None,
        'published_at': None,
        'created_time': datetime(2026, 8, 25, 9, 0, tzinfo=TZ),
        'updated_time': None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_application(**overrides: Any) -> SimpleNamespace:
    base = {'id': 1, 'key': 'myapp', 'name': 'MyApp', 'description': None, 'status': 'enabled'}
    base.update(overrides)
    return SimpleNamespace(**base)


def make_channel(**overrides: Any) -> SimpleNamespace:
    base = {
        'id': 2,
        'application_id': 1,
        'code': 'stable',
        'name': '正式版',
        'status': 'enabled',
        'current_release_id': None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_artifacts(release_id: int = 10) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=1,
            release_id=release_id,
            kind='installer',
            filename='Myapp-0.1.2-win-x64.exe',
            storage_path='myapp/stable/Myapp-0.1.2-win-x64.exe',
            size=100,
            sha256='a' * 64,
            sha512='B' * 88,
        ),
        SimpleNamespace(
            id=2,
            release_id=release_id,
            kind='blockmap',
            filename='Myapp-0.1.2-win-x64.exe.blockmap',
            storage_path='myapp/stable/Myapp-0.1.2-win-x64.exe.blockmap',
            size=10,
            sha256='b' * 64,
            sha512=None,
        ),
        SimpleNamespace(
            id=3,
            release_id=release_id,
            kind='manifest',
            filename='release-manifest-0.1.2.json',
            storage_path='myapp/stable/release-manifest-0.1.2.json',
            size=30,
            sha256='c' * 64,
            sha512=None,
        ),
    ]


@contextmanager
def service_mocks(
    release: SimpleNamespace,
    application: SimpleNamespace | None = None,
    channel: SimpleNamespace | None = None,
    artifacts: list[SimpleNamespace] | None = None,
    *,
    storage_exists: bool = True,
    latest_below: SimpleNamespace | None = None,
    current_release: SimpleNamespace | None = None,
) -> Generator[SimpleNamespace]:
    application = application or make_application()
    channel = channel or make_channel()
    if artifacts is None:
        artifacts = make_artifacts(release.id)

    storage = MagicMock()
    storage.exists.return_value = storage_exists

    with (
        patch.object(rs, 'release_dao') as release_dao,
        patch.object(rs, 'channel_dao') as channel_dao,
        patch.object(rs, 'application_dao') as application_dao,
        patch.object(rs, 'artifact_dao') as artifact_dao,
        patch.object(rs, 'artifact_storage', storage),
    ):
        release_dao.get = AsyncMock(side_effect=lambda db, pk: release if pk == release.id else current_release)
        release_dao.mark_published = AsyncMock(return_value=1)
        release_dao.update_status = AsyncMock(return_value=1)
        release_dao.update_signature_status = AsyncMock(return_value=1)
        release_dao.delete = AsyncMock(return_value=1)
        release_dao.get_latest_published_below = AsyncMock(return_value=latest_below)
        application_dao.get = AsyncMock(return_value=application)
        channel_dao.get = AsyncMock(return_value=channel)
        channel_dao.update_current_release = AsyncMock(return_value=1)
        artifact_dao.get_by_release = AsyncMock(return_value=artifacts)
        artifact_dao.delete_by_release = AsyncMock(return_value=3)
        yield SimpleNamespace(
            release_dao=release_dao,
            channel_dao=channel_dao,
            application_dao=application_dao,
            artifact_dao=artifact_dao,
            storage=storage,
        )


async def test_publish_success_switches_channel_current() -> None:
    release = make_release(status='draft')
    with service_mocks(release) as mocks:
        result = await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)
        assert result.status == 'published'
        mocks.release_dao.mark_published.assert_awaited_once()
        assert mocks.release_dao.mark_published.await_args.kwargs['published_by'] == 99
        mocks.channel_dao.update_current_release.assert_awaited_once()
        assert mocks.channel_dao.update_current_release.await_args.args[2] == release.id


async def test_get_list_includes_artifacts_without_n_plus_one() -> None:
    release = make_release()
    artifact = SimpleNamespace(
        id=1,
        release_id=release.id,
        kind='installer',
        filename='Myapp-0.1.2-win-x64.exe',
        storage_path='myapp/stable/Myapp-0.1.2-win-x64.exe',
        size=100,
        sha256='a' * 64,
        sha512='B' * 88,
    )
    db = MagicMock()
    with (
        patch.object(rs, 'release_dao') as release_dao,
        patch.object(rs, 'artifact_dao') as artifact_dao,
        patch.object(rs, 'paging_data', new_callable=AsyncMock) as paging_data,
    ):
        release_dao.get_detail_select = AsyncMock(return_value=MagicMock())
        paging_data.return_value = {'items': [{'id': release.id}], 'total': 1}
        artifact_dao.get_by_release_ids = AsyncMock(return_value=[artifact])

        result = await rs.release_service.get_list(db=db)

    assert result['items'][0]['artifacts'][0]['kind'] == 'installer'
    assert result['items'][0]['artifacts'][0]['filename'] == 'Myapp-0.1.2-win-x64.exe'
    artifact_dao.get_by_release_ids.assert_awaited_once_with(db, [release.id])
    artifact_dao.get_by_release.assert_not_called()


async def test_publish_rejects_already_published() -> None:
    release = make_release(status='published')
    with service_mocks(release) as mocks:
        with pytest.raises(errors.RequestError):
            await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)
        mocks.release_dao.mark_published.assert_not_awaited()


async def test_publish_rejects_disabled_application_or_channel() -> None:
    release = make_release(status='draft')
    with (
        service_mocks(release, application=make_application(status='disabled')),
        pytest.raises(errors.RequestError),
    ):
        await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)
    with (
        service_mocks(release, channel=make_channel(status='disabled')),
        pytest.raises(errors.RequestError),
    ):
        await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)


async def test_publish_rejects_incomplete_artifacts() -> None:
    release = make_release(status='draft')
    artifacts = [a for a in make_artifacts(release.id) if a.kind != 'blockmap']
    with service_mocks(release, artifacts=artifacts) as mocks:
        with pytest.raises(errors.RequestError):
            await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)
        mocks.release_dao.mark_published.assert_not_awaited()


async def test_publish_rejects_missing_files() -> None:
    release = make_release(status='draft')
    with service_mocks(release, storage_exists=False) as mocks:
        with pytest.raises(errors.RequestError):
            await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)
        mocks.release_dao.mark_published.assert_not_awaited()


async def test_publish_rejects_lower_version_than_current() -> None:
    release = make_release(status='draft', version='0.1.1')
    current = make_release(id=9, version='0.1.2', status='published')
    with service_mocks(release, channel=make_channel(current_release_id=9), current_release=current) as mocks:
        with pytest.raises(errors.RequestError):
            await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)
        mocks.release_dao.mark_published.assert_not_awaited()


async def test_publish_allows_resuming_paused_current() -> None:
    release = make_release(status='paused', version='0.1.2')
    with service_mocks(release, channel=make_channel(current_release_id=release.id), current_release=release) as mocks:
        result = await rs.release_service.publish(db=MagicMock(), pk=release.id, published_by=99)
        assert result.status == 'published'
        mocks.release_dao.mark_published.assert_awaited_once()


async def test_pause_falls_back_to_previous_published() -> None:
    release = make_release(status='published')
    fallback = make_release(id=8, version='0.1.1', status='published')
    with service_mocks(release, channel=make_channel(current_release_id=release.id), latest_below=fallback) as mocks:
        result = await rs.release_service.pause(db=MagicMock(), pk=release.id)
        assert result.status == 'paused'
        assert result.fallback_release_id == fallback.id
        mocks.channel_dao.update_current_release.assert_awaited_once()
        assert mocks.channel_dao.update_current_release.await_args.args[2] == fallback.id


async def test_pause_clears_current_when_no_fallback() -> None:
    release = make_release(status='published')
    with service_mocks(release, channel=make_channel(current_release_id=release.id), latest_below=None) as mocks:
        result = await rs.release_service.pause(db=MagicMock(), pk=release.id)
        assert result.fallback_release_id is None
        mocks.channel_dao.update_current_release.assert_awaited_once()
        assert mocks.channel_dao.update_current_release.await_args.args[2] is None


@pytest.mark.anyio
@pytest.mark.parametrize('current_id', [None, 12])
async def test_pausing_historical_release_does_not_change_current_feed(current_id: int | None) -> None:
    """暂停旧 published 记录不能把较新当前版本清空或降级。"""
    release = make_release(id=10, version='1.0.0', status='published')
    current = make_release(id=12, version='1.2.0', status='published')
    with service_mocks(release, channel=make_channel(current_release_id=current_id), current_release=current) as mocks:
        db = MagicMock()
        result = await rs.release_service.pause(db=db, pk=release.id)
        assert result.status == 'paused'
        assert result.fallback_release_id == current_id
        mocks.release_dao.update_status.assert_awaited_once_with(db, release.id, status='paused')
        mocks.release_dao.get_latest_published_below.assert_not_awaited()
        mocks.channel_dao.update_current_release.assert_not_awaited()


async def test_pause_rejects_non_published() -> None:
    release = make_release(status='draft')
    with service_mocks(release) as mocks:
        with pytest.raises(errors.RequestError):
            await rs.release_service.pause(db=MagicMock(), pk=release.id)
        mocks.release_dao.update_status.assert_not_awaited()


async def test_delete_rejects_published_release() -> None:
    release = make_release(status='published')
    with service_mocks(release) as mocks:
        with pytest.raises(errors.RequestError):
            await rs.release_service.delete(db=MagicMock(), pk=release.id)
        mocks.release_dao.delete.assert_not_awaited()


async def test_delete_rejects_current_release() -> None:
    release = make_release(status='paused')
    with service_mocks(release, channel=make_channel(current_release_id=release.id)) as mocks:
        with pytest.raises(errors.RequestError):
            await rs.release_service.delete(db=MagicMock(), pk=release.id)
        mocks.release_dao.delete.assert_not_awaited()


async def test_delete_removes_files_then_records() -> None:
    release = make_release(status='draft')
    with service_mocks(release) as mocks:
        count = await rs.release_service.delete(db=MagicMock(), pk=release.id)
        assert count == 1
        assert mocks.storage.delete.call_count == 3
        for artifact in make_artifacts(release.id):
            mocks.storage.delete.assert_any_call(artifact.storage_path)
        mocks.artifact_dao.delete_by_release.assert_awaited_once()
        mocks.release_dao.delete.assert_awaited_once()


def build_upload_bytes(*, app_key: str = 'myapp') -> dict[str, bytes]:
    prefix = app_key[:1].upper() + app_key[1:]
    installer_name = f'{prefix}-0.1.2-win-x64.exe'
    blockmap_name = f'{installer_name}.blockmap'
    installer = b'installer-payload'
    blockmap = b'blockmap-payload'
    installer_sha256 = hashlib.sha256(installer).hexdigest()
    installer_sha512 = base64.b64encode(hashlib.sha512(installer).digest()).decode('ascii')
    blockmap_sha256 = hashlib.sha256(blockmap).hexdigest()
    manifest = {
        'schemaVersion': 2,
        'version': '0.1.2',
        'target': 'win32-x64',
        'artifact': {
            'filename': installer_name,
            'bytes': len(installer),
            'sha256': installer_sha256,
            'sha512': installer_sha512,
        },
        'blockmap': {
            'filename': blockmap_name,
            'bytes': len(blockmap),
            'sha256': blockmap_sha256,
        },
        'signature': {'status': 'unsigned'},
    }
    return {
        'installer': installer,
        'blockmap': blockmap,
        'manifest': json.dumps(manifest).encode('utf-8'),
    }


def make_upload_file(data: bytes, filename: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


@contextmanager
def upload_mocks(
    release: SimpleNamespace,
    storage: ArtifactStorage,
    application: SimpleNamespace | None = None,
) -> Generator[MagicMock]:
    with (
        patch.object(rs, 'release_dao') as release_dao,
        patch.object(rs, 'channel_dao') as channel_dao,
        patch.object(rs, 'application_dao') as application_dao,
        patch.object(rs, 'artifact_dao') as artifact_dao,
        patch.object(rs, 'artifact_storage', storage),
    ):
        release_dao.get = AsyncMock(return_value=release)
        release_dao.update_signature_status = AsyncMock(return_value=1)
        application_dao.get = AsyncMock(return_value=application if application is not None else make_application())
        channel_dao.get = AsyncMock(return_value=make_channel())
        artifact_dao.replace_release_artifacts = AsyncMock(return_value=None)
        artifact_dao.get_by_release = AsyncMock(return_value=make_artifacts(release.id))
        yield artifact_dao


async def test_upload_artifacts_success(tmp_path: Path) -> None:
    release = make_release(status='draft')
    storage = ArtifactStorage(tmp_path / 'app_updates')
    storage.ensure_layout()
    payloads = build_upload_bytes()
    with upload_mocks(release, storage) as artifact_dao:
        result = await rs.release_service.upload_artifacts(
            db=MagicMock(),
            pk=release.id,
            installer=make_upload_file(payloads['installer'], 'Myapp-0.1.2-win-x64.exe'),
            blockmap=make_upload_file(payloads['blockmap'], 'Myapp-0.1.2-win-x64.exe.blockmap'),
            manifest=make_upload_file(payloads['manifest'], 'release-manifest.json'),
        )
        assert result.release_id == release.id
        assert result.signature_status == 'unsigned'
        assert result.installer.sha512 is not None
        artifact_dao.replace_release_artifacts.assert_awaited_once()
        assert await to_thread.run_sync(storage.exists, 'myapp/stable/Myapp-0.1.2-win-x64.exe')
        assert await to_thread.run_sync(storage.exists, 'myapp/stable/Myapp-0.1.2-win-x64.exe.blockmap')
        assert await to_thread.run_sync(storage.exists, 'myapp/stable/release-manifest-0.1.2.json')
        assert not await to_thread.run_sync(lambda: list((tmp_path / 'app_updates' / '.staging').iterdir()))


async def test_upload_artifacts_accepts_non_default_application_key(tmp_path: Path) -> None:
    """产物文件名由应用 key 推导，非默认应用同样可以上传发布"""
    release = make_release(status='draft')
    storage = ArtifactStorage(tmp_path / 'app_updates')
    storage.ensure_layout()
    payloads = build_upload_bytes(app_key='myapp')
    with upload_mocks(release, storage, application=make_application(key='myapp', name='MyApp')) as artifact_dao:
        result = await rs.release_service.upload_artifacts(
            db=MagicMock(),
            pk=release.id,
            installer=make_upload_file(payloads['installer'], 'Myapp-0.1.2-win-x64.exe'),
            blockmap=make_upload_file(payloads['blockmap'], 'Myapp-0.1.2-win-x64.exe.blockmap'),
            manifest=make_upload_file(payloads['manifest'], 'release-manifest.json'),
        )
        assert result.release_id == release.id
        artifact_dao.replace_release_artifacts.assert_awaited_once()
        assert await to_thread.run_sync(storage.exists, 'myapp/stable/Myapp-0.1.2-win-x64.exe')
        assert await to_thread.run_sync(storage.exists, 'myapp/stable/Myapp-0.1.2-win-x64.exe.blockmap')
        assert await to_thread.run_sync(storage.exists, 'myapp/stable/release-manifest-0.1.2.json')
        assert not await to_thread.run_sync(lambda: list((tmp_path / 'app_updates' / '.staging').iterdir()))


async def test_upload_artifacts_rejects_bad_installer_name(tmp_path: Path) -> None:
    release = make_release(status='draft')
    storage = ArtifactStorage(tmp_path / 'app_updates')
    storage.ensure_layout()
    payloads = build_upload_bytes()
    with upload_mocks(release, storage) as artifact_dao:
        with pytest.raises(errors.RequestError):
            await rs.release_service.upload_artifacts(
                db=MagicMock(),
                pk=release.id,
                installer=make_upload_file(payloads['installer'], 'Wrong-0.1.2-win-x64.exe'),
                blockmap=make_upload_file(payloads['blockmap'], 'Myapp-0.1.2-win-x64.exe.blockmap'),
                manifest=make_upload_file(payloads['manifest'], 'release-manifest.json'),
            )
        artifact_dao.replace_release_artifacts.assert_not_awaited()
        assert not await to_thread.run_sync(lambda: list((tmp_path / 'app_updates' / '.staging').iterdir()))


async def test_upload_artifacts_rejects_manifest_mismatch(tmp_path: Path) -> None:
    release = make_release(status='draft')
    storage = ArtifactStorage(tmp_path / 'app_updates')
    storage.ensure_layout()
    payloads = build_upload_bytes()
    tampered = json.loads(payloads['manifest'].decode('utf-8'))
    tampered['artifact']['bytes'] += 1
    payloads['manifest'] = json.dumps(tampered).encode('utf-8')
    with upload_mocks(release, storage) as artifact_dao:
        with pytest.raises(errors.RequestError):
            await rs.release_service.upload_artifacts(
                db=MagicMock(),
                pk=release.id,
                installer=make_upload_file(payloads['installer'], 'Myapp-0.1.2-win-x64.exe'),
                blockmap=make_upload_file(payloads['blockmap'], 'Myapp-0.1.2-win-x64.exe.blockmap'),
                manifest=make_upload_file(payloads['manifest'], 'release-manifest.json'),
            )
        artifact_dao.replace_release_artifacts.assert_not_awaited()
        assert not await to_thread.run_sync((tmp_path / 'app_updates' / 'myapp').exists)
        assert not await to_thread.run_sync(lambda: list((tmp_path / 'app_updates' / '.staging').iterdir()))


async def test_upload_artifacts_rejects_non_draft(tmp_path: Path) -> None:
    release = make_release(status='published')
    storage = ArtifactStorage(tmp_path / 'app_updates')
    storage.ensure_layout()
    payloads = build_upload_bytes()
    with upload_mocks(release, storage) as artifact_dao:
        with pytest.raises(errors.RequestError):
            await rs.release_service.upload_artifacts(
                db=MagicMock(),
                pk=release.id,
                installer=make_upload_file(payloads['installer'], 'Myapp-0.1.2-win-x64.exe'),
                blockmap=make_upload_file(payloads['blockmap'], 'Myapp-0.1.2-win-x64.exe.blockmap'),
                manifest=make_upload_file(payloads['manifest'], 'release-manifest.json'),
            )
        artifact_dao.replace_release_artifacts.assert_not_awaited()
