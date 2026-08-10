"""Shopee 适配器：公开搜索 API 尽力直采（反爬失败时降级/自定义数据源）。"""
import json
from typing import List, Optional

from ..config import SHOPEE_RANK_URL
from ..http_utils import read_data_source, fetch_json, fetch_text
from ..models import Product
from ..utils import clean_text, to_float, to_int
from .base import CollectorError, PlatformAdapter
from .env_json import parse_items_json

_BASE = "https://shopee.sg/api/v4/search/search_items"


class ShopeeAdapter(PlatformAdapter):
    platform = "shopee"
    display_name = "Shopee（虾皮）"
    regions = "跨境"
    availability = "尽力抓取（公开搜索 API）"
    supports_search = True
    default_category = "手机"

    def rank_categories(self) -> List[str]:
        return ["手机", "美妆", "女装", "家居", "3C"]

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self.fetch_search(keyword=category or self.default_category, limit=limit)

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        if SHOPEE_RANK_URL:
            raw = read_data_source(SHOPEE_RANK_URL)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as e:
                raise CollectorError(f"Shopee 自定义数据源不是合法 JSON: {e}") from e
            return parse_items_json(payload, platform=self.platform, category=keyword, limit=limit)

        params = {
            "by": "relevancy",
            "keyword": keyword,
            "limit": min(limit, 60),
            "newest": 0,
            "order": "desc",
            "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH",
            "version": 2,
        }
        try:
            payload = fetch_json(_BASE, params=params, headers={"Referer": "https://shopee.sg/"})
        except Exception as e:  # noqa: BLE001
            raise CollectorError(f"Shopee 搜索 API 请求失败（可能被风控）: {e}") from e
        items = (payload.get("data") or {}).get("items") or []
        products: List[Product] = []
        for rank, it in enumerate(items[:limit], start=1):
            item = it.get("item_basic") or it
            pid = str(item.get("itemid") or "")
            if not pid:
                continue
            title = clean_text(item.get("name"))
            # Shopee 价格以整数存储，除以 100000 得到原币种金额
            price_raw = item.get("price") or item.get("price_min") or item.get("price_max")
            price = round(price_raw / 100000.0, 2) if isinstance(price_raw, (int, float)) else None
            sales = to_int(item.get("historical_sold") or item.get("sold"))
            shop = clean_text((it.get("shop_info") or {}).get("shop_name") or item.get("shop_name"))
            products.append(
                Product(
                    platform=self.platform,
                    product_id=pid,
                    title=title or "Unnamed",
                    price=price,
                    sales=sales,
                    sales_text=f"{sales} sold" if sales else None,
                    shop_name=shop,
                    rank=rank,
                    category=keyword,
                    url=f"https://shopee.sg/product/{pid}/",
                )
            )
        if not products:
            raise CollectorError("Shopee 搜索返回为空（可能被风控），已降级")
        return products