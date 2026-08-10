"""京东适配器：公开搜索页/排行榜页（尽力抓取，命中验证码时降级）。"""
from typing import List, Optional

from bs4 import BeautifulSoup

from ..config import JD_RANK_URL, JD_UNION_APP_KEY, JD_UNION_SECRET_KEY, USER_AGENT
from ..http_utils import fetch_text, read_data_source
from ..models import Product
from ..utils import clean_text, to_float, to_int
from .base import CollectorError, PlatformAdapter
from .env_json import parse_items_json
from .jd_union import JDUnionAdapter

_HEADERS = {"Referer": "https://www.jd.com/", "User-Agent": USER_AGENT}


class JDAdapter(PlatformAdapter):
    platform = "jd"
    display_name = "京东"
    regions = "国内"
    availability = "尽力抓取（公开搜索页/排行榜页）"
    supports_search = True
    default_category = "手机"
    rate_limit_sec = 3.0

    def rank_categories(self) -> List[str]:
        return ["手机", "电脑", "家电", "美妆", "食品", "母婴", "服饰"]

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        cat = category or self.default_category
        if JD_RANK_URL:
            return parse_items_json(_load_jd_source(), platform=self.platform, category=cat, limit=limit)
        if JD_UNION_APP_KEY and JD_UNION_SECRET_KEY:
            return JDUnionAdapter().fetch_rank(category=cat, limit=limit)
        url = "https://search.jd.com/Search"
        params = {"keyword": cat, "enc": "utf-8", "wq": cat}
        html = fetch_text(url, params=params, headers=_HEADERS)
        return self._parse_search_html(html, cat, limit)

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        if JD_RANK_URL:
            return parse_items_json(_load_jd_source(), platform=self.platform, category=keyword, limit=limit)
        if JD_UNION_APP_KEY and JD_UNION_SECRET_KEY:
            return JDUnionAdapter().fetch_search(keyword=keyword, limit=limit)
        url = "https://search.jd.com/Search"
        params = {"keyword": keyword, "enc": "utf-8", "wq": keyword}
        html = fetch_text(url, params=params, headers=_HEADERS)
        return self._parse_search_html(html, keyword, limit)

    def _parse_search_html(self, html: str, category: str, limit: int) -> List[Product]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("li.gl-item")
        products: List[Product] = []
        for rank, li in enumerate(items[:limit], start=1):
            sku = li.get("data-sku") or li.get("data-pid")
            if not sku:
                continue
            title_el = li.select_one(".p-name em") or li.select_one(".p-name")
            title = clean_text(title_el.get_text()) if title_el else "未命名商品"
            price_el = li.select_one(".p-price strong i") or li.select_one(".p-price")
            price = to_float(price_el.get_text()) if price_el else None
            shop_el = li.select_one(".p-shop a") or li.select_one(".p-shopnum a")
            shop = clean_text(shop_el.get_text()) if shop_el else None
            commit_el = li.select_one(".p-commit strong a")
            sales = to_int(commit_el.get_text()) if commit_el else None
            products.append(
                Product(
                    platform=self.platform,
                    product_id=str(sku),
                    title=title,
                    price=price,
                    sales=sales,
                    sales_text=f"{sales}+ 条评价" if sales else None,
                    shop_name=shop,
                    rank=rank,
                    category=category,
                    url=f"https://item.jd.com/{sku}.html",
                )
            )
        if not products:
            raise CollectorError("京东页面解析为空（可能触发验证码或页面改版），已降级")
        return products


def _load_jd_source():
    import json

    raw = read_data_source(JD_RANK_URL)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise CollectorError(f"京东自定义数据源不是合法 JSON: {e}") from e
