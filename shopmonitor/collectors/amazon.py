"""Amazon 适配器：公开 Best Sellers 榜单页尽力直采。"""
from typing import List, Optional

from bs4 import BeautifulSoup

from ..config import AMAZON_RANK_URL
from ..http_utils import read_data_source, fetch_text
from ..models import Product
from ..utils import clean_text, to_float
from .base import CollectorError, PlatformAdapter


class AmazonAdapter(PlatformAdapter):
    platform = "amazon"
    display_name = "Amazon（亚马逊）"
    regions = "跨境"
    availability = "尽力抓取（公开 Best Sellers 页面）"
    supports_search = False
    default_category = "All"

    def rank_categories(self) -> List[str]:
        return ["All", "Electronics", "Home & Kitchen", "Beauty", "Sports", "Toys"]

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        cat = category or "All"
        if AMAZON_RANK_URL:
            from .env_json import parse_items_json
            import json
            raw = read_data_source(AMAZON_RANK_URL)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as e:
                raise CollectorError(f"Amazon 自定义数据源不是合法 JSON: {e}") from e
            return parse_items_json(payload, platform=self.platform, category=cat, limit=limit)

        url = "https://www.amazon.com/Best-Sellers/zgbs"
        html = fetch_text(url, headers={"Accept-Language": "en-US,en;q=0.9"})
        return self._parse_bestsellers(html, cat, limit)

    def _parse_bestsellers(self, html: str, category: str, limit: int) -> List[Product]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.zg-grid-general-faceout") or soup.select(
            "div.p13n-gridItem div[id*='p13n-asin']"
        )
        products: List[Product] = []
        for rank, card in enumerate(cards[:limit], start=1):
            link = card.select_one("a.a-link-normal")
            title_el = card.select_one("div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1") or card.select_one(
                "div.p13n-sc-truncate"
            ) or card.select_one("a.a-link-normal div")
            title = clean_text(title_el.get_text()) if title_el else None
            price_el = card.select_one("span._cDEzb_p13n-sc-price_3mJ9Z") or card.select_one("span.p13n-sc-price")
            price = to_float(price_el.get_text()) if price_el else None
            asin = ""
            if link and link.get("href"):
                import re
                m = re.search(r"/dp/([A-Z0-9]{10})", link["href"])
                asin = m.group(1) if m else ""
            if not asin:
                continue
            products.append(
                Product(
                    platform=self.platform,
                    product_id=asin,
                    title=title or "Unnamed",
                    price=price,
                    rank=rank,
                    category=category,
                    url=f"https://www.amazon.com/dp/{asin}",
                )
            )
        if not products:
            raise CollectorError("Amazon Best Sellers 页面解析为空（可能被验证码拦截），已降级")
        return products