"""平台采集适配器。每个平台一个 Adapter，统一接口，可独立替换为官方 API。"""
from .base import CollectorError, PlatformAdapter
from .registry import get_adapter, list_platforms

__all__ = ["CollectorError", "PlatformAdapter", "get_adapter", "list_platforms"]