"""app_update 插件测试配置"""

import inspect
import os

import pytest

pytest_plugins = ['anyio']


@pytest.fixture
def anyio_backend() -> str:
    return 'asyncio'


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """为本插件目录下的 async 测试自动附加 anyio 标记"""
    for item in items:
        in_plugin = 'backend/plugin/app_update' in str(item.fspath).replace('\\', '/')
        if in_plugin and inspect.iscoroutinefunction(item.function) and item.get_closest_marker('anyio') is None:
            item.add_marker(pytest.mark.anyio)


def integration_enabled() -> bool:
    """集成测试需要完整数据库与 Redis 环境，默认跳过"""
    return os.environ.get('FBA_INTEGRATION', '').lower() in ('1', 'true', 'yes')
