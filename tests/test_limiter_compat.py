"""宿主限流接口分支回归，不连接 Redis 或改变限流策略。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.plugin.app_update.utils import limiter


def test_current_host_uses_sdk_without_importing_legacy_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    dependency = Mock()
    current = SimpleNamespace(rate_limit=Mock(return_value=dependency))
    imports = Mock(return_value=current)
    monkeypatch.setattr(limiter, 'find_spec', Mock(return_value=object()))
    monkeypatch.setattr(limiter, 'import_module', imports)
    assert limiter.feed_rate_limit() is dependency
    current.rate_limit.assert_called_once_with('60/minute')
    imports.assert_called_once_with('backend.common.limiter')


def test_legacy_host_retains_existing_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    dependency = Mock()
    rate = Mock()
    legacy = SimpleNamespace(RateLimiter=Mock(return_value=dependency))
    rates = SimpleNamespace(Rate=Mock(return_value=rate), Duration=SimpleNamespace(MINUTE=60000))
    imports = Mock(side_effect=lambda name: {'backend.utils.limiter': legacy, 'pyrate_limiter': rates}[name])
    monkeypatch.setattr(limiter, 'find_spec', Mock(return_value=None))
    monkeypatch.setattr(limiter, 'import_module', imports)
    assert limiter.feed_rate_limit() is dependency
    rates.Rate.assert_called_once_with(60, rates.Duration.MINUTE)
    legacy.RateLimiter.assert_called_once_with(rate)


def test_broken_current_limiter_is_not_silently_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limiter, 'find_spec', Mock(return_value=object()))
    monkeypatch.setattr(limiter, 'import_module', Mock(side_effect=ImportError('broken SDK dependency')))
    with pytest.raises(ImportError, match='broken SDK dependency'):
        limiter.feed_rate_limit()
