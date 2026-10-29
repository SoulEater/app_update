"""严格 x.y.z 版本号解析与比较"""

import re

from backend.common.exception import errors

_VERSION_PATTERN = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')


class SemanticVersion:
    """严格语义化版本，仅支持 x.y.z 三段数字"""

    __slots__ = ('major', 'minor', 'patch')

    def __init__(self, *, major: int, minor: int, patch: int) -> None:
        self.major = major
        self.minor = minor
        self.patch = patch

    def __str__(self) -> str:
        return f'{self.major}.{self.minor}.{self.patch}'

    def __repr__(self) -> str:
        return f'SemanticVersion({self!s})'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._key == other._key

    def __hash__(self) -> int:
        return hash(self._key)

    def __lt__(self, other: 'SemanticVersion') -> bool:
        return self._key < other._key

    def __le__(self, other: 'SemanticVersion') -> bool:
        return self._key <= other._key

    def __gt__(self, other: 'SemanticVersion') -> bool:
        return self._key > other._key

    def __ge__(self, other: 'SemanticVersion') -> bool:
        return self._key >= other._key

    @property
    def _key(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


def parse_version(version: str) -> SemanticVersion:
    """
    解析严格 x.y.z 版本号

    :param version: 版本号字符串
    :return:
    """
    match = _VERSION_PATTERN.fullmatch(version or '')
    if not match:
        raise errors.RequestError(msg=f'版本号必须为 x.y.z 格式，当前值: {version}')
    return SemanticVersion(major=int(match.group(1)), minor=int(match.group(2)), patch=int(match.group(3)))
