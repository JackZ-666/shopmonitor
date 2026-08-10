"""淘宝适配器：公开搜索需登录 Cookie，默认走自定义 JSON 数据源或 Cookie 直采。

接入方式（任选其一）：
- 配置 SHOPMONITOR_TAOBAO_RANK_URL=<返回商品列表 JSON 的接口地址>（推荐，最稳）
- 或配置 TAOBAO_COOKIE=<登录后 Cookie>，走 s.taobao.com 搜索页尽力直采（可能触发滑块）。
"""
import json
import re
from typing import List, Optional

from ..config import TAOBAO_COOKIE
from ..http_utils import read_data_source, fetch_text
from ..models import Product
from ..utils import clean_text, to_float, to_int
from .base import CollectorError, PlatformAdapter
from .env_json import parse_items_json


class TaobaoAdapter(PlatformAdapter):
    platform = "taobao"
    display_name = "淘宝"
    regions = "国内"
    availability = "需配置凭证（Cookie 或自定义 JSON 数据源）"
    supports_search = True
    default_category = "热销榜"

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self.fetch_search(keyword=category or "热销", limit=limit)

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        from ..config import TAOBAO_RANK_URL

        if TAOBAO_RANK_URL:
            raw = read_data_source(TAOBAO_RANK_URL)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as e:
                raise CollectorError(f"淘宝自定义数据源不是合法 JSON: {e}") from e
            return parse_items_json(payload, platform=self.platform, category=keyword, limit=limit)

        if not TAOBAO_COOKIE:
            raise CollectorError(
                "淘宝搜索需要登录态。请配置环境变量 TAOBAO_COOKIE（登录后浏览器 Cookie）"
                "或 SHOPMONITOR_TAOBAO_RANK_URL（自定义 JSON 接口），见 docs/PLATFORM_STATUS.md。"
            )
        url = "https://s.taobao.com/search"
        html = fetch_text(url, params={"q": keyword}, cookies=_cookie_dict(TAOBAO_COOKIE))
        return self._parse_search_html(html, keyword, limit)

    def _parse_search_html(self, html: str, category: str, limit: int) -> List[Product]:
        m = re.search(r"window\.__INIT_DATA__\s*=\s*(\{.*?\});", html, re.S)
        data = json.loads(m.group(1)) if m else None
        products: List[Product] = []
        if data:
            rows = (
                data.get("itemList", {}).get("content", [])
                or data.get("itemlist", [])
                or data.get("items", [])
            )
            for rank, it in enumerate(rows[:limit], start=1):
                item = it.get("item", it)
                pid = str(item.get("itemId") or item.get("nid") or item.get("id") or "")
                if not pid:
                    continue
                title = clean_text(item.get("title") or item.get("rawTitle") or "未命名商品")
                price = to_float(item.get("price") or item.get("priceShow") or item.get("zkPrice"))
                sales = to_int(item.get("realSales") or item.get("monthSales") or item.get("sales"))
                shop = clean_text(item.get("shopName") or item.get("nick") or "")
                products.append(
                    Product(
                        platform=self.platform,
                        product_id=pid,
                        title=title,
                        price=price,
                        sales=sales,
                        sales_text=f"{sales} 人付款" if sales else None,
                        shop_name=shop,
                        rank=rank,
                        category=category,
                        url=f"https://item.taobao.com/item.htm?id={pid}",
                    )
                )
        if not products:
            raise CollectorError("淘宝搜索页解析为空（可能触发滑块验证），已降级")
        return products


def _cookie_dict(cookie: str) -> dict:
    out = {}
    for part in cookie.split(";"):
        if "=" in part:
            k, _, v = part.strip().partition("=")
            out[k.strip()] = v.strip()
    return out