"""适配器基类：所有平台统一实现 fetch_rank / fetch_search / fetch_product。"""
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Product


class CollectorError(RuntimeError):
    """采集失败：反爬拦截 / 网络异常 / 未配置凭证。"""


class PlatformAdapter(ABC):
    platform: str = ""
    display_name: str = ""
    regions: str = ""              # 国内 / 跨境
    availability: str = "尽力抓取"  # 公开可用 / 尽力抓取 / 需配置凭证
    supports_search: bool = True
    default_category: Optional[str] = None
    rate_limit_sec: float = 2.0

    # ---------------- 必须实现 ----------------
    @abstractmethod
    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        """拉取榜单/热卖商品列表。"""

    # ---------------- 可选实现 ----------------
    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        raise CollectorError(f"{self.display_name} 暂不支持关键词搜索")

    def fetch_product(self, product_id: str) -> Product:
        raise CollectorError(f"{self.display_name} 暂不支持按 ID 查询商品详情")

    def rank_categories(self) -> List[str]:
        return []

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} platform={self.platform}>"