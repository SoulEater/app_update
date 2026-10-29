"""release manifest 校验单元测试"""

import base64
import hashlib
import json

from typing import TypedDict, cast

import pytest

from backend.common.exception import errors
from backend.plugin.app_update.utils.manifest import parse_manifest, validate_release_manifest

INSTALLER_BYTES = b'installer-content'
BLOCKMAP_BYTES = b'blockmap-content'
INSTALLER_SHA256 = hashlib.sha256(INSTALLER_BYTES).hexdigest()
INSTALLER_SHA512 = base64.b64encode(hashlib.sha512(INSTALLER_BYTES).digest()).decode('ascii')
BLOCKMAP_SHA256 = hashlib.sha256(BLOCKMAP_BYTES).hexdigest()


class ActualArtifacts(TypedDict):
    release_version: str
    installer_filename: str
    installer_size: int
    installer_sha256: str
    installer_sha512: str
    blockmap_filename: str
    blockmap_size: int
    blockmap_sha256: str


def make_manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        'schemaVersion': 2,
        'version': '0.1.2',
        'target': 'win32-x64',
        'artifact': {
            'filename': 'Myapp-0.1.2-win-x64.exe',
            'bytes': len(INSTALLER_BYTES),
            'sha256': INSTALLER_SHA256,
            'sha512': INSTALLER_SHA512,
        },
        'blockmap': {
            'filename': 'Myapp-0.1.2-win-x64.exe.blockmap',
            'bytes': len(BLOCKMAP_BYTES),
            'sha256': BLOCKMAP_SHA256,
        },
        'signature': {'status': 'unsigned'},
    }
    manifest.update(overrides)
    return manifest


def make_actual() -> ActualArtifacts:
    return {
        'release_version': '0.1.2',
        'installer_filename': 'Myapp-0.1.2-win-x64.exe',
        'installer_size': len(INSTALLER_BYTES),
        'installer_sha256': INSTALLER_SHA256,
        'installer_sha512': INSTALLER_SHA512,
        'blockmap_filename': 'Myapp-0.1.2-win-x64.exe.blockmap',
        'blockmap_size': len(BLOCKMAP_BYTES),
        'blockmap_sha256': BLOCKMAP_SHA256,
    }


def test_parse_manifest_valid() -> None:
    parsed = parse_manifest(content=json.dumps(make_manifest()).encode('utf-8'))
    assert parsed['schemaVersion'] == 2


@pytest.mark.parametrize(
    'raw',
    [
        b'not-json',
        b'[]',
        b'"string"',
        b'123',
        b'null',
    ],
)
def test_parse_manifest_invalid(raw: bytes) -> None:
    with pytest.raises(errors.RequestError):
        parse_manifest(content=raw)


def test_parse_manifest_depth_exceeded() -> None:
    deep: dict[str, object] = {
        'schemaVersion': 2,
        'version': '0.1.2',
        'target': 'win32-x64',
        'artifact': {},
        'blockmap': {},
        'signature': {},
    }
    node = deep
    for _ in range(6):
        child: dict[str, object] = {}
        node['nested'] = child
        node = child
    with pytest.raises(errors.RequestError):
        parse_manifest(content=json.dumps(deep).encode('utf-8'))


def test_validate_success_returns_signature_status() -> None:
    status = validate_release_manifest(manifest=make_manifest(), **make_actual())
    assert status == 'unsigned'


def test_validate_signature_status_none_allowed() -> None:
    manifest = make_manifest(signature={'status': None})
    assert validate_release_manifest(manifest=manifest, **make_actual()) is None


@pytest.mark.parametrize('schema_version', [1, '2', None, 2.0, True])
def test_validate_rejects_bad_schema_version(schema_version: str | float | None) -> None:
    with pytest.raises(errors.RequestError):
        validate_release_manifest(manifest=make_manifest(schemaVersion=schema_version), **make_actual())


@pytest.mark.parametrize('version', ['0.1.1', '0.1.3', None])
def test_validate_rejects_version_mismatch(version: str | None) -> None:
    with pytest.raises(errors.RequestError):
        validate_release_manifest(manifest=make_manifest(version=version), **make_actual())


@pytest.mark.parametrize('target', ['darwin-arm64', 'win32-ia32', None])
def test_validate_rejects_bad_target(target: str | None) -> None:
    with pytest.raises(errors.RequestError):
        validate_release_manifest(manifest=make_manifest(target=target), **make_actual())


@pytest.mark.parametrize(
    'field, value',
    [
        ('filename', 'Other.exe'),
        ('bytes', len(INSTALLER_BYTES) + 1),
        ('sha256', '0' * 64),
        ('sha512', 'not-base64-sha512'),
    ],
)
def test_validate_rejects_artifact_mismatch(field: str, value: str | int) -> None:
    artifact = dict(cast('dict[str, object]', make_manifest()['artifact']))
    artifact[field] = value
    with pytest.raises(errors.RequestError):
        validate_release_manifest(manifest=make_manifest(artifact=artifact), **make_actual())


@pytest.mark.parametrize(
    'field, value',
    [
        ('filename', 'other.blockmap'),
        ('bytes', len(BLOCKMAP_BYTES) + 1),
        ('sha256', 'f' * 64),
    ],
)
def test_validate_rejects_blockmap_mismatch(field: str, value: str | int) -> None:
    blockmap = dict(cast('dict[str, object]', make_manifest()['blockmap']))
    blockmap[field] = value
    with pytest.raises(errors.RequestError):
        validate_release_manifest(manifest=make_manifest(blockmap=blockmap), **make_actual())


@pytest.mark.parametrize(
    'field',
    ['artifact', 'blockmap', 'signature'],
)
def test_validate_rejects_non_dict_sections(field: str) -> None:
    with pytest.raises(errors.RequestError):
        validate_release_manifest(manifest=make_manifest(**{field: 'bad'}), **make_actual())


@pytest.mark.parametrize('status', [1, [], {}, True, 'x' * 33])
def test_validate_rejects_invalid_signature_status(status: object) -> None:
    with pytest.raises(errors.RequestError):
        validate_release_manifest(manifest=make_manifest(signature={'status': status}), **make_actual())


@pytest.mark.parametrize('field', ['publisherName', 'installerThumbprint', 'applicationThumbprint', 'timestampSubject'])
@pytest.mark.parametrize('value', [1, [], {}, True, 'x' * 1025])
def test_validate_rejects_invalid_signature_claim(field: str, value: object) -> None:
    with pytest.raises(errors.RequestError):
        validate_release_manifest(
            manifest=make_manifest(signature={'status': 'unknown', field: value}),
            **make_actual(),
        )


def test_parse_manifest_limits_array_depth() -> None:
    with pytest.raises(errors.RequestError):
        parse_manifest(content=b'{"nested": [[[[[[]]]]]]}')


def test_parse_manifest_handles_json_parser_recursion_limit() -> None:
    with pytest.raises(errors.RequestError):
        parse_manifest(content=b'{"nested":' + b'[' * 2000 + b']' * 2000 + b'}')
