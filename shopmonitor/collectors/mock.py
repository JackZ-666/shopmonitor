"""演示适配器：不联网、确定性生成数据，用于本地试跑/测试/上架演示。

也用作真实平台采集失败时的降级数据源（degraded=True 会明确标注）。
字段覆盖主流电商监控维度：价格/销量/排名/评分/评论数/库存/促销/店铺评分。
"""
import hashlib
from typing import List, Optional

from ..models import Product
from .base import PlatformAdapter

_CATEGORIES = ["数码", "美妆", "服饰", "食品", "家居", "母婴"]
_SHOPS = ["旗舰店", "专营店", "官方店", "优选店"]
_STOCK = ["现货", "现货", "现货", "预售", "缺货"]
_PROMOS = [None, "限时秒杀 -15%", "领券立减 ¥20", "满 300 减 40", None, None]


def _seed(platform: str, category: str, i: int) -> int:
    return int(hashlib.md5(f"{platform}:{category}:{i}".encode()).hexdigest()[:8], 16)


class MockAdapter(PlatformAdapter):
    platform = "mock"
    display_name = "演示数据"
    regions = "全部"
    availability = "公开可用（演示）"
    supports_search = True

    def __init__(self, platform: str = "mock", base_price: float = 99.0):
        self.platform = platform
        self.display_name = f"{platform}（演示）"
        self.base_price = base_price

    def rank_categories(self) -> List[str]:
        return list(_CATEGORIES)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        cat = (category or "数码").strip() or "数码"
        limit = min(limit, 100)
        items: List[Product] = []
        for i in range(1, limit + 1):
            s = _seed(self.platform, cat, i)
            price = round(self.base_price + (s % 900) / 10.0, 2)
            sales = int(s % 5000) + 1
            rating = round(3.5 + (s % 15) / 10.0, 1)
            promo = _PROMOS[s % len(_PROMOS)]
            items.append(
                Product(
                    platform=self.platform,
                    product_id=f"demo-{cat}-{i:04d}",
                    title=f"{cat}商品 {i:02d}（演示）",
                    price=price,
                    original_price=round(price * 1.25, 2),
                    sales=sales,
                    sales_text=f"{sales} 件已售",
                    shop_name=_SHOPS[s % len(_SHOPS)],
                    shop_rating=round(4.0 + (s % 10) / 10.0, 1),
                    brand=f"{cat}品牌{s % 5 + 1}",
                    rating=rating,
                    review_count=int(s % 800) + 20,
                    stock_status=_STOCK[s % len(_STOCK)],
                    promo_text=promo,
                    is_promo=promo is not None,
                    rank=i,
                    category=cat,
                    url=f"https://example.com/{self.platform}/{cat}/{i}",
                    image=f"https://example.com/img/{self.platform}/{i}.jpg",
                )
            )
        return items

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        cat = (keyword or "数码").strip() or "数码"
        return self.fetch_rank(category=cat, limit=limit)

    def fetch_product(self, product_id: str) -> Product:
        parts = product_id.split("-")
        cat = parts[1] if len(parts) > 1 else "数码"
        idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        s = _seed(self.platform, cat, idx)
        price = round(self.base_price + (s % 900) / 10.0, 2)
        promo = _PROMOS[s % len(_PROMOS)]
        return Product(
            platform=self.platform,
            product_id=product_id,
            title=f"{cat}商品 {idx:02d}（演示）",
            price=price,
            original_price=round(price * 1.25, 2),
            sales=int(s % 5000) + 1,
            sales_text=f"{int(s % 5000) + 1} 件已售",
            shop_name=_SHOPS[s % len(_SHOPS)],
            shop_rating=round(4.0 + (s % 10) / 10.0, 1),
            brand=f"{cat}品牌{s % 5 + 1}",
            rating=round(3.5 + (s % 15) / 10.0, 1),
            review_count=int(s % 800) + 20,
            stock_status=_STOCK[s % len(_STOCK)],
            promo_text=promo,
            is_promo=promo is not None,
            rank=idx,
            category=cat,
            url=f"https://example.com/{self.platform}/{cat}/{idx}",
        )