"""安装产物存储单元测试"""

import base64
import hashlib
import io

from pathlib import Path
from unittest.mock import patch

import pytest

from anyio import to_thread
from fastapi import UploadFile

from backend.common.exception import errors
from backend.plugin.app_update.utils.artifact_storage import ArtifactStorage, base64_encode, safe_filename


def make_upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


def expected_digests(data: bytes) -> tuple[str, str]:
    sha256 = hashlib.sha256(data).hexdigest()
    sha512 = base64.b64encode(hashlib.sha512(data).digest()).decode('ascii')
    return sha256, sha512


@pytest.fixture
def storage(tmp_path: Path) -> ArtifactStorage:
    root = tmp_path / 'app_updates'
    instance = ArtifactStorage(root)
    instance.ensure_layout()
    return instance


@pytest.mark.parametrize(
    'filename',
    ['Myapp-0.1.2-win-x64.exe', 'release-manifest.json', 'a-b_c.d-1'],
)
def test_safe_filename_accepts(filename: str) -> None:
    assert safe_filename(filename=filename) == filename


@pytest.mark.parametrize(
    'filename',
    [
        '',
        None,
        '..',
        '.',
        '../evil.exe',
        'dir/evil.exe',
        'dir\\\\evil.exe',
        'evil name.exe',
        'evil.exe ',
        '.hidden',
        '中文名.exe',
    ],
)
def test_safe_filename_rejects(filename: str | None) -> None:
    with pytest.raises(errors.RequestError):
        safe_filename(filename=filename)


def test_resolve_within_root_accepts_nested(storage: ArtifactStorage) -> None:
    resolved = storage.resolve_within_root('myapp/stable/file.exe')
    assert str(resolved).startswith(str(storage.root))


def test_resolve_within_root_rejects_escape(storage: ArtifactStorage) -> None:
    with pytest.raises(errors.ForbiddenError):
        storage.resolve_within_root('../outside.exe')
    with pytest.raises(errors.ForbiddenError):
        storage.resolve_within_root('myapp/../../outside.exe')


def test_resolve_within_root_rejects_absolute(storage: ArtifactStorage, tmp_path: Path) -> None:
    with pytest.raises(errors.ForbiddenError):
        storage.resolve_within_root(tmp_path / 'x.exe')


async def test_stream_upload_computes_digests(storage: ArtifactStorage) -> None:
    data = b'x' * 1024 * 257
    staging = storage.new_staging_dir()
    staged = await storage.stream_upload(
        upload_file=make_upload(data, 'Myapp-0.1.2-win-x64.exe'),
        staging_dir=staging,
        filename='Myapp-0.1.2-win-x64.exe',
        max_bytes=1024 * 1024,
    )
    sha256, sha512 = expected_digests(data)
    assert staged.size == len(data)
    assert staged.sha256 == sha256
    assert staged.sha512 == sha512
    assert await to_thread.run_sync(staged.path.is_file)
    storage.cleanup_staging(staging)


async def test_stream_upload_rejects_oversize_and_cleans_partial(storage: ArtifactStorage) -> None:
    staging = storage.new_staging_dir()
    with pytest.raises(errors.RequestError):
        await storage.stream_upload(
            upload_file=make_upload(b'x' * 1024, 'big.exe'),
            staging_dir=staging,
            filename='big.exe',
            max_bytes=64,
        )
    assert not await to_thread.run_sync((staging / 'big.exe').exists)
    storage.cleanup_staging(staging)


async def test_stream_upload_rejects_empty_file(storage: ArtifactStorage) -> None:
    staging = storage.new_staging_dir()
    with pytest.raises(errors.RequestError):
        await storage.stream_upload(
            upload_file=make_upload(b'', 'empty.exe'),
            staging_dir=staging,
            filename='empty.exe',
            max_bytes=64,
        )
    assert not await to_thread.run_sync((staging / 'empty.exe').exists)
    storage.cleanup_staging(staging)


async def test_promote_moves_atomically(storage: ArtifactStorage) -> None:
    staging = storage.new_staging_dir()
    staged = await storage.stream_upload(
        upload_file=make_upload(b'content', 'Myapp-0.1.2-win-x64.exe'),
        staging_dir=staging,
        filename='Myapp-0.1.2-win-x64.exe',
        max_bytes=1024,
    )
    final = storage.promote(staged_path=staged.path, final_relative='myapp/stable/Myapp-0.1.2-win-x64.exe')
    assert await to_thread.run_sync(final.is_file)
    assert not await to_thread.run_sync(staged.path.exists)
    assert await to_thread.run_sync(storage.exists, 'myapp/stable/Myapp-0.1.2-win-x64.exe')
    storage.cleanup_staging(staging)


async def test_promote_refuses_overwrite(storage: ArtifactStorage) -> None:
    staging = storage.new_staging_dir()
    staged = await storage.stream_upload(
        upload_file=make_upload(b'one', 'a.exe'),
        staging_dir=staging,
        filename='a.exe',
        max_bytes=1024,
    )
    storage.promote(staged_path=staged.path, final_relative='myapp/stable/a.exe')

    staging2 = storage.new_staging_dir()
    staged2 = await storage.stream_upload(
        upload_file=make_upload(b'two', 'a.exe'),
        staging_dir=staging2,
        filename='a.exe',
        max_bytes=1024,
    )
    with pytest.raises(errors.RequestError):
        storage.promote(staged_path=staged2.path, final_relative='myapp/stable/a.exe')
    storage.cleanup_staging(staging)
    storage.cleanup_staging(staging2)


async def test_delete_only_within_root(storage: ArtifactStorage) -> None:
    staging = storage.new_staging_dir()
    staged = await storage.stream_upload(
        upload_file=make_upload(b'gone', 'a.exe'),
        staging_dir=staging,
        filename='a.exe',
        max_bytes=1024,
    )
    storage.promote(staged_path=staged.path, final_relative='myapp/stable/a.exe')
    storage.delete('myapp/stable/a.exe')
    assert not await to_thread.run_sync(storage.exists, 'myapp/stable/a.exe')
    with pytest.raises(errors.ForbiddenError):
        storage.delete('../outside.exe')
    storage.cleanup_staging(staging)


def test_base64_encode() -> None:
    assert base64_encode(b'ab') == 'YWI='


def test_promote_cannot_overwrite_a_concurrent_target(storage: ArtifactStorage) -> None:
    """原子 no-clobber 操作不能被独立 exists 检查的竞态绕过。"""
    staged = storage.new_staging_dir() / 'a.exe'
    staged.write_bytes(b'new')
    final = storage.resolve_within_root('demo/stable/a.exe')
    final.parent.mkdir(parents=True)
    final.write_bytes(b'old')
    with patch.object(Path, 'exists', return_value=False), pytest.raises(errors.RequestError):
        storage.promote(staged_path=staged, final_relative='demo/stable/a.exe')
    assert final.read_bytes() == b'old'
    assert staged.read_bytes() == b'new'
