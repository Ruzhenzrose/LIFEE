"""pytest 配置"""
import pytest


# 设置 pytest-asyncio 默认模式
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
