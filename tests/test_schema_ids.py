"""主键和关联 ID 的 JSON 无损序列化回归。"""

import os
import subprocess
import sys

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pydantic import BaseModel

from backend.plugin.app_update.schema.application import GetApplicationDetail
from backend.plugin.app_update.schema.artifact import GetArtifactDetail, UploadArtifactResult
from backend.plugin.app_update.schema.base import settings
from backend.plugin.app_update.schema.channel import GetChannelDetail
from backend.plugin.app_update.schema.release import GetReleaseDetail, PauseReleaseResult, PublishReleaseResult

IDENTIFIER = 880210000000000001
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def response_models() -> list[BaseModel]:
    """模型输入仍保留 Python int，只在对外序列化时转换。"""
    artifact = GetArtifactDetail(
        id=IDENTIFIER,
        release_id=IDENTIFIER,
        kind='installer',
        filename='Demo-1.0.0-win-x64.exe',
        storage_path='demo/stable/Demo-1.0.0-win-x64.exe',
        size=123,
        sha256='a' * 64,
    )
    return [
        GetApplicationDetail(id=IDENTIFIER, key='demo', name='Demo', status='enabled', created_time=NOW),
        GetChannelDetail(
            id=IDENTIFIER,
            application_id=IDENTIFIER,
            application_name='Demo',
            code='stable',
            name='Stable',
            status='enabled',
            current_release_id=IDENTIFIER,
            feed_url='https://example.com/updates/demo/stable/',
            created_time=NOW,
        ),
        GetReleaseDetail(
            id=IDENTIFIER,
            application_id=IDENTIFIER,
            application_key='demo',
            application_name='Demo',
            channel_id=IDENTIFIER,
            channel_code='stable',
            channel_name='Stable',
            version='1.0.0',
            platform='win32',
            arch='x64',
            status='draft',
            published_by=IDENTIFIER,
            created_time=NOW,
            artifacts=[artifact],
        ),
        artifact,
        UploadArtifactResult(release_id=IDENTIFIER, installer=artifact, blockmap=artifact, manifest=artifact),
        PublishReleaseResult(
            release_id=IDENTIFIER, version='1.0.0', status='published', previous_release_id=IDENTIFIER
        ),
        PauseReleaseResult(release_id=IDENTIFIER, version='1.0.0', status='paused', fallback_release_id=IDENTIFIER),
    ]


@pytest.mark.parametrize('mode', ['autoincrement', 'snowflake'])
def test_every_entity_id_preserves_precision(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'DATABASE_PK_MODE', mode)
    expected = str(IDENTIFIER) if mode == 'snowflake' else IDENTIFIER
    for model in response_models():
        payload = model.model_dump(mode='json')
        for name, value in payload.items():
            if name == 'id' or name.endswith('_id') or name == 'published_by':
                assert value == expected
        if isinstance(model, GetReleaseDetail):
            assert payload['artifacts'][0]['release_id'] == expected
            assert payload['artifacts'][0]['id'] == expected
        if isinstance(model, UploadArtifactResult):
            assert payload['installer']['id'] == expected
            assert payload['blockmap']['release_id'] == expected


@pytest.mark.parametrize('mode', ['autoincrement', 'snowflake'])
def test_nullable_ids_remain_null(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'DATABASE_PK_MODE', mode)
    result = PauseReleaseResult(release_id=1, version='1.0.0', status='paused', fallback_release_id=None)
    assert result.model_dump(mode='json')['fallback_release_id'] is None


def test_snowflake_serializers_when_host_is_imported_in_snowflake_mode() -> None:
    """独立进程验证条件定义的宿主 serializer，防止多继承覆盖漏掉外键。"""
    code = """
from backend.plugin.app_update.tests.test_schema_ids import response_models, IDENTIFIER
from backend.plugin.app_update.schema.release import CreateReleaseParam
for model in response_models():
    for name, value in model.model_dump(mode='json').items():
        if (name == 'id' or name.endswith('_id') or name == 'published_by') and value is not None:
            assert value == str(IDENTIFIER), (type(model).__name__, name)
param = CreateReleaseParam(application_id=str(IDENTIFIER), channel_id=str(IDENTIFIER), version='1.0.0')
assert param.application_id == IDENTIFIER
"""
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=Path(__file__).resolve().parents[4],
        env=os.environ | {'DATABASE_PK_MODE': 'snowflake', 'PYTHONIOENCODING': 'utf-8'},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
