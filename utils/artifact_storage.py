"""安装产物流式存储

- staging 目录位于存储根目录内，上传完成后原子移动到正式目录
- 读取 UploadFile 时按块流式处理，禁止一次性读入内存
- 所有路径必须经 resolve 校验，禁止目录穿越
"""

import base64
import hashlib
import os
import re
import uuid

from dataclasses import dataclass
from pathlib import Path

import anyio

from fastapi import UploadFile

from backend.common.exception import errors
from backend.core.path_conf import BASE_PATH
from backend.plugin.app_update.config import app_update_settings as settings

_SAFE_FILENAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')


@dataclass(frozen=True)
class StagedArtifact:
    """staging 中待转正的产物"""

    path: Path
    filename: str
    size: int
    sha256: str
    sha512: str


def get_storage_root() -> Path:
    """解析存储根目录，相对路径基于 backend/ 目录"""
    raw = Path(settings.APP_UPDATE_STORAGE_DIR)
    return raw.resolve() if raw.is_absolute() else (BASE_PATH / raw).resolve()


def safe_filename(*, filename: str | None) -> str:
    """
    提取安全文件名，拒绝路径成分与非法字符

    :param filename: 客户端提供的原始文件名
    :return:
    """
    if not filename:
        raise errors.RequestError(msg='文件名不能为空')
    normalized = filename.replace('\\', '/')
    if '/' in normalized:
        raise errors.RequestError(msg=f'文件名不允许包含路径成分: {filename}')
    name = normalized
    if not name or name in {'.', '..'} or not _SAFE_FILENAME_PATTERN.fullmatch(name):
        raise errors.RequestError(msg=f'非法的文件名: {filename}')
    return name


class ArtifactStorage:
    """安装产物存储管理"""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def resolve_within_root(self, relative: str | Path) -> Path:
        """
        解析存储根目录内的相对路径，禁止越界

        :param relative: 相对存储根目录的路径
        :return:
        """
        candidate = Path(relative)
        if candidate.is_absolute():
            raise errors.ForbiddenError(msg='禁止提交绝对路径')
        target = (self._root / candidate).resolve()
        try:
            target.relative_to(self._root)
        except ValueError as e:
            raise errors.ForbiddenError(msg='非法的文件路径') from e
        return target

    def ensure_layout(self) -> None:
        """创建存储根目录与 staging 目录"""
        (self._root / '.staging').mkdir(parents=True, exist_ok=True)

    def new_staging_dir(self) -> Path:
        """创建随机 staging 目录"""
        staging_dir = self.resolve_within_root(Path('.staging') / f'upload-{uuid.uuid4().hex}')
        staging_dir.mkdir(parents=True, exist_ok=False)
        return staging_dir

    def cleanup_staging(self, staging_dir: Path) -> None:
        """清理 staging 目录及其全部内容"""
        try:
            resolved = staging_dir.resolve()
            resolved.relative_to((self._root / '.staging').resolve())
        except ValueError:
            return
        for child in resolved.rglob('*'):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
        for child in sorted(resolved.rglob('*'), reverse=True):
            if child.is_dir():
                child.rmdir()
        resolved.rmdir()

    async def stream_upload(
        self,
        *,
        upload_file: UploadFile,
        staging_dir: Path,
        filename: str,
        max_bytes: int,
    ) -> StagedArtifact:
        """
        流式写入 staging 并复算摘要

        :param upload_file: FastAPI 上传文件
        :param staging_dir: staging 目录
        :param filename: 已通过安全校验的文件名
        :param max_bytes: 大小上限
        :return:
        """
        target_path = staging_dir / filename
        sha256 = hashlib.sha256()
        sha512 = hashlib.sha512()
        size = 0
        try:
            async with await anyio.open_file(target_path, 'wb') as f:
                while True:
                    chunk = await upload_file.read(settings.APP_UPDATE_UPLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise errors.RequestError(msg=f'文件 {filename} 超过大小上限 {max_bytes} 字节')
                    sha256.update(chunk)
                    sha512.update(chunk)
                    await f.write(chunk)
                if size == 0:
                    raise errors.RequestError(msg=f'文件 {filename} 为空')
                await f.flush()
                await anyio.to_thread.run_sync(os.fsync, f.fileno())
        except Exception:
            await anyio.Path(target_path).unlink(missing_ok=True)
            raise
        return StagedArtifact(
            path=target_path,
            filename=filename,
            size=size,
            sha256=sha256.hexdigest(),
            sha512=base64_encode(sha512.digest()),
        )

    def promote(self, *, staged_path: Path, final_relative: str | Path) -> Path:
        """
        原子移动 staging 文件到正式目录，目标存在时拒绝覆盖

        :param staged_path: staging 内的文件路径
        :param final_relative: 正式目录相对路径
        :return:
        """
        final_path = self.resolve_within_root(final_relative)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # 同一存储根目录中原子建立链接，目标存在即失败，避免 exists/replace 的并发覆盖窗口。
            os.link(staged_path, final_path)
        except FileExistsError as exc:
            raise errors.RequestError(msg=f'目标文件已存在，禁止覆盖: {final_path.name}') from exc
        try:
            staged_path.unlink()
        except OSError:
            final_path.unlink(missing_ok=True)
            raise
        return final_path

    def exists(self, relative: str | Path) -> bool:
        """判断正式目录文件是否存在"""
        return self.resolve_within_root(relative).is_file()

    def delete(self, relative: str | Path) -> None:
        """删除正式目录文件，路径越界时拒绝"""
        target = self.resolve_within_root(relative)
        target.unlink(missing_ok=True)


def base64_encode(digest: bytes) -> str:
    """摘要字节转 Base64 字符串"""
    return base64.b64encode(digest).decode('ascii')


artifact_storage = ArtifactStorage(get_storage_root())
