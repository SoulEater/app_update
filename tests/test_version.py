"""版本号解析与比较单元测试"""

import pytest

from backend.common.exception import errors
from backend.plugin.app_update.utils.version import parse_version


def test_parse_valid_version() -> None:
    version = parse_version('0.1.2')
    assert (version.major, version.minor, version.patch) == (0, 1, 2)
    assert str(version) == '0.1.2'


@pytest.mark.parametrize('raw', ['1.2.3', '0.0.0', '10.20.30'])
def test_parse_more_valid_versions(raw: str) -> None:
    assert str(parse_version(raw)) == raw


@pytest.mark.parametrize(
    'raw',
    [
        '',
        '1.2',
        '1.2.3.4',
        'v1.2.3',
        '1.2.x',
        '1.2.3-beta',
        ' 1.2.3',
        '1.2.3 ',
        '一.二.三',
    ],
)
def test_parse_invalid_version(raw: str) -> None:
    with pytest.raises(errors.RequestError):
        parse_version(raw)


def test_version_ordering() -> None:
    assert parse_version('0.1.9') < parse_version('0.2.0')
    assert parse_version('0.9.9') < parse_version('1.0.0')
    assert parse_version('1.0.0') < parse_version('1.0.1')
    assert parse_version('2.0.0') > parse_version('1.99.99')
    assert parse_version('1.0.0') == parse_version('1.0.0')
    assert parse_version('1.0.0') <= parse_version('1.0.0')
    assert parse_version('1.0.0') >= parse_version('1.0.0')


def test_version_hash_and_eq() -> None:
    assert parse_version('3.4.5') == parse_version('3.4.5')
    assert len({parse_version('3.4.5'), parse_version('3.4.5')}) == 1
