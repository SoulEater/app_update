"""复用宿主限流机制，同时兼容 FBA 1.16 SDK 与旧版 RateLimiter。"""

from collections.abc import Awaitable, Callable
from importlib import import_module
from importlib.util import find_spec


def feed_rate_limit() -> Callable[..., Awaitable[None]]:
    """每 IP 每分钟 60 次；缺少实现时启动失败，绝不静默关闭限流。"""
    if find_spec('backend.common.limiter') is not None:
        module = import_module('backend.common.limiter')
        return module.rate_limit('60/minute')

    module = import_module('backend.utils.limiter')
    rates = import_module('pyrate_limiter')
    return module.RateLimiter(rates.Rate(60, rates.Duration.MINUTE))
