"""Exercise the standalone CLI and validate its output with the real backend validator."""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys

from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

import pytest

from backend.plugin.app_update.utils.manifest import parse_manifest, validate_release_manifest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'generate_manifest.py'
INSTALLER = b'fictional installer\x00' * 100000  # Cross the CLI chunk boundary.
BLOCKMAP = b'fictional blockmap\n'

CliRunner: TypeAlias = Callable[..., subprocess.CompletedProcess[str]]
CliFixture: TypeAlias = tuple[CliRunner, Path, Path, Path]


@pytest.fixture
def cli(tmp_path: Path) -> CliFixture:
    # Copy only the script, and use isolated Python: no repository imports/site packages.
    script = tmp_path / 'generate_manifest.py'
    shutil.copyfile(SCRIPT, script)
    installer = tmp_path / 'Myapp-1.2.3-win-x64.exe'
    blockmap = tmp_path / 'Myapp-1.2.3-win-x64.exe.blockmap'
    installer.write_bytes(INSTALLER)
    blockmap.write_bytes(BLOCKMAP)
    output = tmp_path / 'release-manifest-1.2.3.json'

    def run(*extra: str | Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                '-I',
                str(script),
                '--application-key',
                'myapp',
                '--version',
                '1.2.3',
                '--installer',
                str(installer),
                '--blockmap',
                str(blockmap),
                '--output',
                str(output),
                *map(str, extra),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

    return run, installer, blockmap, output


def assert_accepted(output: Path, expected_status: str) -> dict[str, object]:
    manifest = parse_manifest(content=output.read_bytes())
    assert manifest['signature']['status'] == expected_status
    assert (
        validate_release_manifest(
            manifest=manifest,
            release_version='1.2.3',
            installer_filename='Myapp-1.2.3-win-x64.exe',
            installer_size=len(INSTALLER),
            installer_sha256=hashlib.sha256(INSTALLER).hexdigest(),
            installer_sha512=base64.b64encode(hashlib.sha512(INSTALLER).digest()).decode('ascii'),
            blockmap_filename='Myapp-1.2.3-win-x64.exe.blockmap',
            blockmap_size=len(BLOCKMAP),
            blockmap_sha256=hashlib.sha256(BLOCKMAP).hexdigest(),
        )
        == expected_status
    )
    return manifest


def assert_cli_error(result: subprocess.CompletedProcess[str], message: str) -> None:
    assert result.returncode == 2, result.stderr
    assert 'error:' in result.stderr
    assert message in result.stderr
    assert 'Traceback' not in result.stderr


def test_default_unknown_and_real_backend_hash_validation(cli: CliFixture) -> None:
    run, _, _, output = cli
    result = run()
    assert result.returncode == 0, result.stderr
    assert assert_accepted(output, 'unknown')['signature'] == {'status': 'unknown'}


@pytest.mark.parametrize('status', [None, 'valid', 'unsigned', 'unknown'])
def test_explicit_signature_declaration(cli: CliFixture, tmp_path: Path, status: str | None) -> None:
    run, _, _, output = cli
    signature = {
        'publisherName': 'FICTIONAL publisher',
        'installerThumbprint': 'FICTIONAL installer',
        'applicationThumbprint': 'FICTIONAL application',
        'timestampSubject': 'FICTIONAL timestamp',
    }
    if status is not None:
        signature['status'] = status
    declaration = tmp_path / 'signature.json'
    declaration.write_text(json.dumps(signature), encoding='utf-8')
    result = run('--signature-file', declaration)
    assert result.returncode == 0, result.stderr
    expected = {'status': 'unknown', **signature}
    assert assert_accepted(output, expected['status'])['signature'] == expected


@pytest.mark.parametrize(
    'content, message',
    [
        ('not-json', 'valid JSON'),
        ('[]', 'JSON object'),
        ('{"extra":"ignored?"}', 'unsupported signature field'),
        ('{"status":true}', 'signature.status must be a string'),
        ('{"status":null}', 'signature.status must be a string'),
        ('{"status":" "}', 'must not be empty'),
        (json.dumps({'status': 's' * 33}), 'at most 32'),
        (json.dumps({'publisherName': 'p' * 1025}), 'at most 1024'),
        (json.dumps({'installerThumbprint': 123}), 'must be a string'),
        (json.dumps({'applicationThumbprint': []}), 'must be a string'),
        (json.dumps({'timestampSubject': {}}), 'must be a string'),
        (' ' * 65537, 'exceeds 65536'),
    ],
    ids=[
        'json',
        'array',
        'extra',
        'boolean',
        'null',
        'empty',
        'status_length',
        'publisher_length',
        'thumbprint_number',
        'thumbprint_array',
        'timestamp_object',
        'file_size',
    ],
)
def test_bad_signature_declarations(cli: CliFixture, tmp_path: Path, content: str, message: str) -> None:
    run, _, _, output = cli
    declaration = tmp_path / 'signature.json'
    declaration.write_text(content, encoding='utf-8')
    assert_cli_error(run('--signature-file', declaration), message)
    assert not output.exists()


@pytest.mark.parametrize(
    'flag, value, message',
    [
        ('--application-key', 'Myapp', 'application key'),
        ('--application-key', 'x', 'application key'),
        ('--application-key', '../app', 'application key'),
        ('--application-key', 'a' * 65, 'application key'),
        ('--version', 'v1.2.3', 'strict x.y.z'),
        ('--version', '1.2.3-beta', 'strict x.y.z'),
        ('--version', '1.2', 'strict x.y.z'),
        ('--version', '１.２.３', 'strict x.y.z'),
        ('--version', '1.2.3\n', 'strict x.y.z'),
        ('--installer', 'Other.exe', 'installer filename'),
        ('--blockmap', 'Other.blockmap', 'blockmap filename'),
    ],
)
def test_invalid_identity_and_names(cli: CliFixture, flag: str, value: str, message: str) -> None:
    run, _, _, output = cli
    assert_cli_error(run(flag, value), message)
    assert not output.exists()


@pytest.mark.parametrize('which', [1, 2])
@pytest.mark.parametrize('missing', [False, True])
def test_empty_or_missing_artifact(cli: CliFixture, which: int, *, missing: bool) -> None:
    run, installer, blockmap, output = cli
    source = {1: installer, 2: blockmap}[which]
    if missing:
        source.unlink()
    else:
        source.write_bytes(b'')
    assert_cli_error(run(), 'regular file' if missing else 'must not be empty')
    assert not output.exists()


def test_output_requires_force(cli: CliFixture) -> None:
    run, _, _, output = cli
    output.write_text('keep me', encoding='utf-8')
    assert_cli_error(run(), 'output already exists')
    assert output.read_text(encoding='utf-8') == 'keep me'
    result = run('--force')
    assert result.returncode == 0, result.stderr
    assert_accepted(output, 'unknown')


@pytest.mark.parametrize('which', ['installer', 'blockmap', 'signature'])
def test_force_never_overwrites_inputs(cli: CliFixture, tmp_path: Path, which: str) -> None:
    run, installer, blockmap, _ = cli
    signature = tmp_path / 'signature.json'
    signature.write_text('{"status":"unknown"}', encoding='utf-8')
    source = {'installer': installer, 'blockmap': blockmap, 'signature': signature}[which]
    before = source.read_bytes()
    assert_cli_error(
        run('--signature-file', signature, '--output', source, '--force'),
        'must not overwrite',
    )
    assert source.read_bytes() == before


@pytest.mark.parametrize('link_kind', ['hardlink', 'symlink'])
def test_output_input_alias_protection(cli: CliFixture, tmp_path: Path, link_kind: str) -> None:
    run, installer, _, _ = cli
    alias = tmp_path / 'alias.json'
    try:
        if link_kind == 'hardlink':
            os.link(installer, alias)
        else:
            alias.symlink_to(installer)
    except OSError as exc:
        pytest.skip(f'filesystem does not support {link_kind}: {exc}')
    assert_cli_error(run('--output', alias, '--force'), 'must not overwrite')
    assert installer.read_bytes() == INSTALLER


def test_bad_output_directory(cli: CliFixture, tmp_path: Path) -> None:
    run, _, _, _ = cli
    assert_cli_error(run('--output', tmp_path / 'missing' / 'manifest.json'), 'error:')
    assert not list(tmp_path.glob('tmp*'))
