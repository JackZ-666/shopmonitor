"""自定义 JSON 数据源解析：任何平台把接口返回转成统一结构即可无缝接入。

支持两种结构：
1) {"items": [ {...}, ... ]}
2) [ {...}, ... ]

每个 item 支持字段别名（自动识别）：
- product_id: product_id / id / sku / item_id / nid
- title: title / name / goods_name
- price: price / current_price / sale_price
- sales: sales / sales_volume / sold / month_sales / 销量
- shop_name: shop_name / shop / store / nick
- shop_rating: shop_rating / store_rating / shop_score
- brand: brand / 品牌
- rating: rating / score / 评分
- review_count: review_count / comment_count / reviews / 评论数
- stock_status: stock_status / stock / 库存状态 / 是否现货
- promo_text: promo_text / promotion / 促销
- is_promo: is_promo / promo / has_promo
- rank: rank / sort
- url: url / link / product_url
"""
from typing import List, Optional

from ..models import Product
from ..utils import clean_text, to_float, to_int
from .base import CollectorError


def parse_items_json(payload, *, platform: str, category: Optional[str], limit: int) -> List[Product]:
    items = _extract_items(payload)
    if not items:
        raise CollectorError(f"{platform} 自定义数据源返回为空 items")
    products: List[Product] = []
    for rank, it in enumerate(items[:limit], start=1):
        if not isinstance(it, dict):
            continue
        pid = _first(it, "product_id", "id", "sku", "item_id", "nid", "goods_id")
        if pid is None:
            continue
        title = clean_text(_first(it, "title", "name", "goods_name"))
        price = to_float(_first(it, "price", "current_price", "sale_price", "price_now"))
        sales = to_int(_first(it, "sales", "sales_volume", "sold", "month_sales", "sale_count"))
        shop = clean_text(_first(it, "shop_name", "shop", "store", "nick"))
        url = clean_text(_first(it, "url", "link", "product_url"))
        image = clean_text(_first(it, "image", "img", "cover"))
        promo = clean_text(_first(it, "promo_text", "promotion", "promo"))
        stock = clean_text(_first(it, "stock_status", "stock", "stock_text"))
        is_promo_raw = _first(it, "is_promo", "promo", "has_promo")
        products.append(
            Product(
                platform=platform,
                product_id=str(pid),
                title=title or "未命名商品",
                price=price,
                sales=sales,
                sales_text=f"{sales} 件已售" if sales else None,
                shop_name=shop,
                shop_rating=to_float(_first(it, "shop_rating", "store_rating", "shop_score")),
                brand=clean_text(_first(it, "brand")),
                rating=to_float(_first(it, "rating", "score")),
                review_count=to_int(_first(it, "review_count", "comment_count", "reviews")),
                stock_status=stock or None,
                promo_text=promo or None,
                is_promo=_as_bool(is_promo_raw),
                rank=rank,
                category=category,
                url=url,
                image=image,
            )
        )
    if not products:
        raise CollectorError(f"{platform} 自定义数据源没有可识别字段（需含 product_id/id/sku）")
    return products


def _as_bool(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y", "是", "有"}


def _extract_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("list") or payload.get("data") or payload.get("result")
        if isinstance(items, dict):
            items = items.get("items") or items.get("list") or items.get("data") or items.get("records")
        if isinstance(items, list):
            return items
    return []


def _first(d: dict, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None