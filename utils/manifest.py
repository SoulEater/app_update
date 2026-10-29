"""release manifest 解析与校验

服务端不信任 manifest 中的任何摘要，全部复算后对比
"""

import json

from typing import Any

from backend.common.exception import errors

MANIFEST_MAX_DEPTH = 4


def _ensure_dict(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise errors.RequestError(msg=f'release manifest 字段 {field} 必须为对象')
    return value


def _check_depth(value: Any, depth: int = 1) -> None:
    """限制 manifest 嵌套深度，拒绝异常结构"""
    if depth > MANIFEST_MAX_DEPTH:
        raise errors.RequestError(msg='release manifest 嵌套深度超限')
    if isinstance(value, dict):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


def parse_manifest(*, content: bytes) -> dict[str, Any]:
    """
    解析 release manifest JSON

    :param content: 原始 JSON 字节
    :return:
    """
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as e:
        raise errors.RequestError(msg='release manifest 不是合法的 JSON') from e
    if not isinstance(parsed, dict):
        raise errors.RequestError(msg='release manifest 顶层必须为 JSON 对象')
    _check_depth(parsed)
    return parsed


def _validate_signature(signature: dict[str, Any]) -> str | None:
    """限制入库状态长度和用于展示的声明字段，不执行验签。"""
    status = signature.get('status')
    if status is not None and (not isinstance(status, str) or len(status) > 32):
        raise errors.RequestError(msg='release manifest signature.status 必须为不超过 32 字符的字符串')
    for field in ('publisherName', 'installerThumbprint', 'applicationThumbprint', 'timestampSubject'):
        value = signature.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 1024):
            raise errors.RequestError(msg=f'release manifest signature.{field} 必须为不超过 1024 字符的字符串或 null')
    return status


def validate_release_manifest(
    *,
    manifest: dict[str, Any],
    release_version: str,
    installer_filename: str,
    installer_size: int,
    installer_sha256: str,
    installer_sha512: str,
    blockmap_filename: str,
    blockmap_size: int,
    blockmap_sha256: str,
) -> str | None:
    """
    校验 manifest 内容与服务器复算结果一致

    :param manifest: 解析后的 manifest 对象
    :param release_version: 版本号
    :param installer_filename: 安装包安全文件名
    :param installer_size: 安装包实际字节数
    :param installer_sha256: 安装包实际 SHA-256（小写十六进制）
    :param installer_sha512: 安装包实际 SHA-512（Base64）
    :param blockmap_filename: blockmap 安全文件名
    :param blockmap_size: blockmap 实际字节数
    :param blockmap_sha256: blockmap 实际 SHA-256（小写十六进制）
    :return: signature.status，用于展示
    """
    if type(manifest.get('schemaVersion')) is not int or manifest['schemaVersion'] != 2:
        raise errors.RequestError(msg='release manifest schemaVersion 必须为 2')
    if manifest.get('version') != release_version:
        raise errors.RequestError(msg='release manifest version 与版本号不一致')
    if manifest.get('target') != 'win32-x64':
        raise errors.RequestError(msg='release manifest target 必须为 win32-x64')

    artifact = _ensure_dict(manifest.get('artifact'), field='artifact')
    expected_artifact = {
        'filename': installer_filename,
        'bytes': installer_size,
        'sha256': installer_sha256,
        'sha512': installer_sha512,
    }
    for field, expected in expected_artifact.items():
        if artifact.get(field) != expected:
            raise errors.RequestError(msg=f'release manifest artifact.{field} 与安装包实际值不一致')

    blockmap = _ensure_dict(manifest.get('blockmap'), field='blockmap')
    expected_blockmap = {
        'filename': blockmap_filename,
        'bytes': blockmap_size,
        'sha256': blockmap_sha256,
    }
    for field, expected in expected_blockmap.items():
        if blockmap.get(field) != expected:
            raise errors.RequestError(msg=f'release manifest blockmap.{field} 与 blockmap 实际值不一致')

    return _validate_signature(_ensure_dict(manifest.get('signature'), field='signature'))
