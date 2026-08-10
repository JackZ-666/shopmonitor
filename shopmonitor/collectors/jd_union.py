"""京东联盟开放平台官方 API 适配器（router.jd.com）。

签名规范：sign = MD5(appSecret + 参数排序拼接 + appSecret)（大写）
- 系统参数：method / app_key / timestamp(yyyy-MM-dd HH:mm:ss) / format=json / v=1.0 / sign_method=md5 / 360buy_param_json
- 业务参数放入 360buy_param_json（JSON 字符串）
- 返回 queryResult 为 JSON 字符串，需二次解析
- 依赖：配置 JD_UNION_APP_KEY + JD_UNION_SECRET_KEY（配置文件.env 或环境变量）
"""
import hashlib
import json
import time
from datetime import datetime
from typing import List, Optional

from ..config import JD_UNION_APP_KEY, JD_UNION_ELITE_ID, JD_UNION_SECRET_KEY, REQUEST_TIMEOUT
from ..http_utils import fetch_text, post_form
from ..models import Product
from ..utils import clean_text, to_float, to_int
from .base import CollectorError, PlatformAdapter

ROUTER_URL = "https://api.jd.com/routerjson"

# goods.query 支持返回的字段（按需取）
_FIELDS = [
    "skuId", "skuName", "price", "inOrderCount30Days", "comments", "goodComments",
    "shopName", "shopInfo", "categoryInfo", "imageInfo", "commissionInfo", "owner",
]


def _now_ms() -> str:
    """京东时间戳：yyyy-MM-dd HH:mm:ss.SSS+0800（毫秒级）。"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}" + "+0800"

def jd_sign(params: dict, secret: str) -> str:
    """京东联盟签名：参数按 key 字典序排序 -> key+value 拼接 -> md5(secret + 拼接 + secret) 大写。"""
    items = sorted((k, str(v)) for k, v in params.items() if k != "sign")
    raw = "".join(f"{k}{v}" for k, v in items)
    return hashlib.md5((secret + raw + secret).encode("utf-8")).hexdigest().upper()


def jd_request(method: str, biz_params: dict) -> dict:
    """调用京东联盟 API 并解析（自动处理 queryResult 二次解析）。"""
    if not JD_UNION_APP_KEY or not JD_UNION_SECRET_KEY:
        raise CollectorError("未配置京东联盟 JD_UNION_APP_KEY / JD_UNION_SECRET_KEY")
    sys_params = {
        "method": method,
        "app_key": JD_UNION_APP_KEY,
        "timestamp": _now_ms(),
        "format": "json",
        "v": "1.0",
        "sign_method": "md5",
        "360buy_param_json": json.dumps(biz_params, ensure_ascii=False),
    }
    sys_params["sign"] = jd_sign(sys_params, JD_UNION_SECRET_KEY)
    text = post_form(ROUTER_URL, sys_params, timeout=REQUEST_TIMEOUT)
    try:
        resp = json.loads(text)
    except json.JSONDecodeError as e:
        raise CollectorError(f"京东联盟返回非 JSON: {e}") from e
    # 统一取第一个 *_responce 节点
    node = None
    for k, v in resp.items():
        if k.endswith("_responce") and isinstance(v, dict):
            node = v
            break
    if node is None:
        raise CollectorError(f"京东联盟响应缺少 responce 节点: {str(resp)[:200]}")
    if str(node.get("code")) not in ("0", "200"):
        raise CollectorError(f"京东联盟错误 code={node.get('code')}: {node.get('message')}")
    result_raw = node.get("queryResult") or node.get("result")
    if isinstance(result_raw, str):
        result = json.loads(result_raw)
    else:
        result = result_raw or {}
    if result.get("code") not in (0, 200, "0", "200", None):
        raise CollectorError(f"京东联盟业务错误 code={result.get('code')}: {result.get('message')}")
    return result


class JDUnionAdapter(PlatformAdapter):
    """官方 API 适配器：京东榜单/搜索/详情。"""

    platform = "jd"
    display_name = "京东（官方 API）"
    regions = "国内"
    availability = "官方 API（已配置 appKey/secretKey）"
    supports_search = True
    default_category = "手机"
    rate_limit_sec = 1.0

    def rank_categories(self) -> List[str]:
        return ["手机", "电脑", "家电", "美妆", "食品", "母婴", "服饰"]

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        cat = category or self.default_category
        biz = {
            "keyword": cat,
            "pageIndex": 1,
            "pageSize": min(limit, 100),
            "fields": _FIELDS,
            "sortName": "inOrderCount30Days",
            "sortType": "desc",
        }
        if JD_UNION_ELITE_ID:
            biz = {"eliteId": JD_UNION_ELITE_ID, "pageIndex": 1, "pageSize": min(limit, 100), "fields": _FIELDS}
        result = jd_request("jd.union.open.goods.query", biz)
        return self._parse_items(result, cat)

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        biz = {"keyword": keyword, "pageIndex": 1, "pageSize": min(limit, 100), "fields": _FIELDS}
        result = jd_request("jd.union.open.goods.query", biz)
        return self._parse_items(result, keyword)

    def fetch_product(self, product_id: str) -> Product:
        # 详情接口：bigfield.query；这里先用 goods.query 按 skuId 关键词兜底
        result = jd_request("jd.union.open.goods.query", {"keyword": product_id, "pageIndex": 1, "pageSize": 1, "fields": _FIELDS})
        items = self._parse_items(result, "商品")
        for it in items:
            if it.product_id == product_id:
                return it
        raise CollectorError(f"京东联盟未找到商品 {product_id}")

    def _parse_items(self, result: dict, category: str) -> List[Product]:
        rows = result.get("data") or []
        products: List[Product] = []
        for rank, g in enumerate(rows[:100], start=1):
            sku = str(g.get("skuId") or "")
            if not sku:
                continue
            price = to_float(g.get("price"))
            shop_info = g.get("shopInfo") or {}
            cat_info = g.get("categoryInfo") or {}
            img_info = g.get("imageInfo") or {}
            images = img_info.get("imageList") or []
            products.append(
                Product(
                    platform=self.platform,
                    product_id=sku,
                    title=clean_text(g.get("skuName")),
                    price=price,
                    sales=to_int(g.get("inOrderCount30Days")),
                    sales_text=f"30天销量 {g.get('inOrderCount30Days')}" if g.get("inOrderCount30Days") is not None else None,
                    shop_name=clean_text(g.get("shopName") or shop_info.get("shopName")),
                    brand=clean_text(g.get("brandName")),
                    rating=to_float(g.get("goodCommentsShare")),
                    review_count=to_int(g.get("comments")),
                    stock_status="现货" if str(g.get("stock", "")).lower() in ("1", "true", "有货") else None,
                    rank=rank,
                    category=clean_text(cat_info.get("cid1Name")) or category,
                    url=f"https://item.jd.com/{sku}.html",
                    image=images[0].get("url") if images else None,
                )
            )
        if not products:
            raise CollectorError("京东联盟返回为空（检查 keyword/eliteId 或账号权限）")
        return products
