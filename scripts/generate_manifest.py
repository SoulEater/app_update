"""Generate schemaVersion=2 release manifests using only the Python standard library.

Signature fields are build-side declarations, never OS signature verification results.
This script can be copied and run outside the backend repository.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import tempfile

from pathlib import Path
from typing import TypedDict

CHUNK_BYTES = 1024 * 1024
SIGNATURE_MAX_BYTES = 64 * 1024
SIGNATURE_FIELDS = {
    'status': 32,
    'publisherName': 1024,
    'installerThumbprint': 1024,
    'applicationThumbprint': 1024,
    'timestampSubject': 1024,
}


class ArtifactHashes(TypedDict):
    filename: str
    bytes: int
    sha256: str


class ArtifactDeclaration(ArtifactHashes, total=False):
    sha512: str


class ReleaseManifest(TypedDict):
    schemaVersion: int
    version: str
    target: str
    artifact: ArtifactDeclaration
    blockmap: ArtifactDeclaration
    signature: dict[str, str]


class ManifestError(ValueError):
    """Invalid inputs or unsafe output destination."""


def read_signature(path: Path | None) -> dict[str, str]:
    """Read a bounded, explicitly supplied build-side declaration."""
    signature = {'status': 'unknown'}
    if path is None:
        return signature
    with path.open('rb') as stream:
        content = stream.read(SIGNATURE_MAX_BYTES + 1)
    if len(content) > SIGNATURE_MAX_BYTES:
        raise ManifestError('signature file exceeds 65536 bytes')
    try:
        declaration = json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError('signature file must contain valid JSON') from exc
    if not isinstance(declaration, dict):
        raise ManifestError('signature file must contain a JSON object')
    for field, value in declaration.items():
        if field not in SIGNATURE_FIELDS:
            raise ManifestError(f'unsupported signature field: {field}')
        if not isinstance(value, str) or len(value) > SIGNATURE_FIELDS[field]:
            raise ManifestError(f'signature.{field} must be a string of at most {SIGNATURE_FIELDS[field]} characters')
        if field == 'status' and not value.strip():
            raise ManifestError('signature.status must not be empty')
        signature[field] = value
    return signature


def hash_artifact(path: Path, *, include_sha512: bool = False) -> ArtifactDeclaration:
    """Hash artifacts in bounded chunks, counting the actual bytes read."""
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512() if include_sha512 else None
    size = 0
    if not path.is_file():
        raise ManifestError(f'input must be a regular file: {path}')
    with path.open('rb') as stream:
        while chunk := stream.read(CHUNK_BYTES):
            size += len(chunk)
            sha256.update(chunk)
            if sha512 is not None:
                sha512.update(chunk)
    if size == 0:
        raise ManifestError(f'input must not be empty: {path}')
    result: ArtifactDeclaration = {'filename': path.name, 'bytes': size, 'sha256': sha256.hexdigest()}
    if sha512 is not None:
        result['sha512'] = base64.b64encode(sha512.digest()).decode('ascii')
    return result


def check_output(output: Path, inputs: list[Path], *, force: bool) -> None:
    """Reject input aliases (including hardlinks) even when --force is supplied."""
    for source in inputs:
        if output.resolve() == source.resolve() or (output.exists() and source.exists() and output.samefile(source)):
            raise ManifestError('output must not overwrite an installer, blockmap or signature input')
    if output.is_symlink():
        raise ManifestError('output must not be a symbolic link')
    if output.exists() and (not force or not output.is_file()):
        raise ManifestError('output already exists; use --force to replace a regular file')


def write_manifest(output: Path, manifest: ReleaseManifest, inputs: list[Path], *, force: bool) -> None:
    """Publish a complete temporary file atomically; no-force never clobbers a file."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(manifest, stream, ensure_ascii=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        check_output(output, inputs, force=force)
        if force:
            os.replace(temporary, output)
        else:
            # Unlike rename on POSIX, link fails atomically if output already exists.
            os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_identity(application_key: str, version: str, installer: Path, blockmap: Path) -> None:
    """Validate release identity and the matching artifact names."""
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,63}', application_key):
        raise ManifestError('application key must be 2-64 lowercase letters, digits, underscores or hyphens')
    if len(version) > 32 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ManifestError('version must be strict x.y.z (ASCII digits only, at most 32 characters)')
    prefix = application_key[:1].upper() + application_key[1:]
    expected = f'{prefix}-{version}-win-x64.exe'
    if installer.name != expected:
        raise ManifestError(f'installer filename must be {expected}')
    if blockmap.name != f'{expected}.blockmap':
        raise ManifestError(f'blockmap filename must be {expected}.blockmap')


def main(argv: list[str] | None = None) -> int:
    """Validate CLI inputs and generate the server-compatible manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application-key', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--installer', required=True, type=Path)
    parser.add_argument('--blockmap', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument(
        '--signature-file', type=Path, help='Build-side declaration only; no OS verification is performed'
    )
    parser.add_argument('--force', action='store_true', help='Replace an existing output file, never an input')
    args = parser.parse_args(argv)
    try:
        validate_identity(args.application_key, args.version, args.installer, args.blockmap)
        inputs = [args.installer, args.blockmap]
        if args.signature_file is not None:
            inputs.append(args.signature_file)
        check_output(args.output, inputs, force=args.force)
        signature = read_signature(args.signature_file)
        manifest: ReleaseManifest = {
            'schemaVersion': 2,
            'version': args.version,
            'target': 'win32-x64',
            'artifact': hash_artifact(args.installer, include_sha512=True),
            'blockmap': hash_artifact(args.blockmap),
            'signature': signature,
        }
        write_manifest(args.output, manifest, inputs, force=args.force)
    except (ManifestError, OSError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f'Manifest written: {args.output} (signature is a declaration, not OS verification)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
