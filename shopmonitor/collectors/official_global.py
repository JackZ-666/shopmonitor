"""官方开放平台适配器（跨境）：TikTok Shop / Amazon PA-API 5.0 / Shopee 开放平台 / AliExpress 联盟。

设计原则（与国内官方适配器 official.py 完全一致）：
- 凭证没配齐 -> 抛 CollectorError，上层框架自动降级为演示数据（degraded=true），流程不中断。
- 凭证配齐 -> 按各平台官方文档生成签名/Token，发起真实请求，解析成统一 Product。
- 官方返回错误/欠费/风控/签名错误 -> 同样映射为 CollectorError（自动降级，不崩服务）。
- 所有签名与解析函数均为纯函数，可离线单测。

签名规范（按官方文档 / 主流 SDK 实现，均已备注来源）：
- TikTok Shop: 查询参数带 app_key/timestamp/version/sign；sign = HMAC-SHA256(app_secret,
    app_secret + path + 业务参数升序 key+value + (body JSON 可选) + app_secret) hex 小写。
    （参考官方「Sign your API request」与 npm tiktok-shop-client 实现，202309 版本）
- Amazon PA-API 5.0: POST JSON，AWS SigV4 签名（Authorization / X-Amz-Date / x-amz-target）。
- Shopee 开放平台 v2: sign = HMAC-SHA256(partner_key, partner_id + api_path + timestamp
    + access_token + shop_id) hex 小写，参数放 query。
- AliExpress 联盟: TOP 淘宝同款签名 md5(secret + 参数 ASCII 升序 key+value + secret) 大写。
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import List, Optional, Tuple

from ..http_utils import fetch_text, post_json
from ..models import Product
from ..utils import clean_text, to_float, to_int
from .base import CollectorError
from .official import OfficialAdapter, _fen2yuan, _loads, md5_sign


# ---------------------------------------------------------------------------
# 纯函数签名工具（便于单测，不联网）
# ---------------------------------------------------------------------------
def tiktok_sign(app_secret: str, path: str, params: dict, body: Optional[dict] = None) -> str:
    """TikTok Shop Open API 签名（202309 版本，query-param 风格）。

    sign = HMAC-SHA256(app_secret, app_secret + path + 业务参数升序 key+value + body + app_secret) hex 小写。
    - 参与签名的参数剔除：app_secret / token / access_token / sign
    - path 含版本段，如 /product/202309/products/search
    - body 为可选 JSON（无则不加）
    来源：官方「Sign your API request」+ npm tiktok-shop-client (common.signature)
    """
    skip = {"app_secret", "token", "access_token", "sign"}
    items = sorted(
        (k, str(v)) for k, v in params.items() if k not in skip and v not in (None, "")
    )
    joined = "".join(f"{k}{v}" for k, v in items)
    body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body else ""
    raw = f"{app_secret}{path}{joined}{body_text}{app_secret}"
    return hmac.new(app_secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def shopee_sign(
    partner_key: str,
    partner_id: str,
    api_path: str,
    timestamp: str,
    access_token: str,
    shop_id: str,
) -> str:
    """Shopee 开放平台 v2 签名。

    base = partner_id + api_path + timestamp + access_token + shop_id
    sign = HMAC-SHA256(partner_key, base) hex 小写。
    来源：open.shopee.com Developer Guide（签名算法）
    """
    base = f"{partner_id}{api_path}{timestamp}{access_token}{shop_id}"
    return hmac.new(partner_key.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()


def _uri_encode(s: str) -> str:
    """RFC3986 百分号编码（AWS SigV4 规范；保留 unreserved 字符）。"""
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_.~":
            out.append(ch)
        else:
            for b in ch.encode("utf-8"):
                out.append(f"%{b:02X}")
    return "".join(out)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def aws_sigv4_headers(
    access_key: str,
    secret_key: str,
    region: str,
    service: str,
    host: str,
    uri: str,
    payload: dict,
    method: str = "POST",
    extra_headers: Optional[dict] = None,
) -> dict:
    """AWS SigV4 签名，返回需要附加的请求头（Authorization / X-Amz-Date）。

    适用于 Amazon PA-API 5.0 等 REST API。返回的 header 与调用方传入的
    Content-Type / Host / x-amz-target 一起组成完整请求头。
    来源：AWS Signature Version 4 signing process（官方文档）
    """
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    payload_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_hash = _sha256_hex(payload_str.encode("utf-8"))
    canonical_uri = "/" + "/".join(_uri_encode(seg) for seg in uri.strip("/").split("/"))

    headers = {
        "content-type": "application/json; charset=utf-8",
        "host": host,
        "x-amz-date": amz_date,
        **(extra_headers or {}),
    }
    # 固定参与签名的 header（x-amz-target 等额外 header 不参与签名，但会随请求发出）
    signed_header_names = ["content-type", "host", "x-amz-date"]
    canonical_headers = "".join(
        f"{name}:{headers[name].strip()}\n" for name in sorted(signed_header_names)
    )
    signed_headers = ";".join(sorted(signed_header_names))

    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            "",  # canonical query（PA-API 走 POST JSON，无 query）
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )

    k_date = _hmac(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {"Authorization": authorization, "X-Amz-Date": amz_date}


# ---------------------------------------------------------------------------
# 1) TikTok Shop 开放平台 —— 商家商品搜索/榜单
# ---------------------------------------------------------------------------
class TikTokShopAdapter(OfficialAdapter):
    """TikTok Shop Open API：商家商品搜索（product/202309/products/search）。

    - 需 App Key / App Secret（TikTok Shop Partner Center 应用）
    - 需商家授权 access_token 与 shop_cipher（可选 shop_id）
    - 签名：query-param 风格 HMAC-SHA256（见 tiktok_sign）
    """

    platform = "tiktok_shop"
    display_name = "TikTok Shop（官方 API）"
    regions = "跨境"
    availability = "官方 API（已配置 AppKey/Secret + 授权 Token）"
    supports_search = True
    default_category = "全部商品"
    credential_keys = ("TIKTOK_SHOP_APP_KEY", "TIKTOK_SHOP_APP_SECRET")
    BASE = "https://open-api.tiktokglobalshop.com"
    VERSION = "202309"
    rate_limit_sec = 1.0

    def rank_categories(self) -> List[str]:
        return ["全部商品", "服饰", "美妆", "数码", "家居", "食品", "母婴"]

    def _call_search(self, keyword: str, page: int, page_size: int) -> List[Product]:
        app_key, secret = self._get_credentials()
        token = os.environ.get("TIKTOK_SHOP_ACCESS_TOKEN", "")
        if not token:
            raise CollectorError(
                "TikTok Shop 接口需要 access_token：请在 TikTok Shop Partner Center "
                "应用授权商家后，把 token 填到 TIKTOK_SHOP_ACCESS_TOKEN（接口文档 → 配置中心 → 官方开放平台凭证（跨境））。"
            )
        shop_cipher = os.environ.get("TIKTOK_SHOP_SHOP_CIPHER", "")
        shop_id = os.environ.get("TIKTOK_SHOP_SHOP_ID", "")

        path = f"/product/{self.VERSION}/products/search"
        timestamp = str(int(datetime.now().timestamp()))
        query = {
            "access_token": token,
            "app_key": app_key,
            "shop_cipher": shop_cipher,
            "shop_id": shop_id,
            "version": self.VERSION,
            "keyword": keyword,
            "page_no": page,
            "page_size": page_size,
        }
        body = {"keyword": keyword, "page_no": page, "page_size": page_size}
        query["timestamp"] = timestamp
        query["sign"] = tiktok_sign(secret, path, query, body)
        url = self.BASE + path
        headers = {"x-tts-access-token": token}
        text = post_json(url + "?" + urlencode(query), body, headers=headers)
        resp = _loads(text, self.display_name)
        if resp.get("code") not in (0, None, "0"):
            raise CollectorError(f"TikTok Shop 错误 code={resp.get('code')}: {resp.get('message')}")
        data = resp.get("data") or {}
        rows = data.get("products") if isinstance(data, dict) else data
        if isinstance(rows, dict):
            rows = rows.get("products") or rows.get("list") or []
        return self._parse_items(rows or [], keyword, page_size)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_search(category or self.default_category, 1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        return self._call_search(keyword, 1, min(limit, 100))

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("id") or g.get("product_id") or "")
            if not pid:
                continue
            imgs = g.get("main_image") or g.get("images") or []
            if isinstance(imgs, dict):
                imgs = imgs.get("url_list") or []
            img = imgs[0] if isinstance(imgs, list) and imgs else None
            price = None
            skus = g.get("skus") or []
            if isinstance(skus, list) and skus and isinstance(skus[0], dict):
                price = _fen2yuan(to_float(skus[0].get("price")))  # TikTok 价格单位：分
            if price is None:
                price = _fen2yuan(to_float(g.get("price")))
            products.append(
                Product(
                    platform="tiktok_shop",
                    product_id=pid,
                    title=clean_text(g.get("name") or g.get("title") or "未命名商品"),
                    price=price,
                    original_price=_fen2yuan(to_float(g.get("original_price") or g.get("market_price"))),
                    sales=to_int(g.get("sales") or g.get("sold")),
                    sales_text=f"销量 {g.get('sales')}" if g.get("sales") is not None else None,
                    shop_name=clean_text(g.get("shop_name") or "TikTok Shop"),
                    stock_status="现货" if str(g.get("status", "")).upper() == "ACTIVE" else None,
                    rank=rank,
                    category=clean_text(g.get("category_name") or g.get("category")) or category,
                    url=f"https://shop.tiktok.com/view/product/{pid}",
                    image=img,
                )
            )
        if not products:
            raise CollectorError("TikTok Shop 返回为空（检查 AppKey/Secret 权限与 token 是否过期）")
        return products


# ---------------------------------------------------------------------------
# 2) Amazon PA-API 5.0 —— SearchItems（关键词搜索/热卖）
# ---------------------------------------------------------------------------
_REGION_HOST = {
    "us-east-1": "webservices.amazon.com",
    "us-west-2": "webservices.amazon.co.jp",
    "eu-west-1": "webservices.amazon.co.uk",
}
_SERVICE = "ProductAdvertisingAPIv1"
_TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"
_RESOURCES = [
    "ItemInfo.Title",
    "ItemInfo.ByLineInfo.Brand",
    "Offers.Listings.Price",
    "Offers.Summaries.LowestPrice",
    "Images.Primary.Large",
    "BrowseNodeInfo.BrowseNodes.DisplayName",
    "ItemInfo.Classifications.Binding",
]


class AmazonOpenAdapter(OfficialAdapter):
    """Amazon PA-API 5.0：SearchItems（需 AWS AccessKey/SecretKey + 联盟 PartnerTag）。"""

    platform = "amazon_open"
    display_name = "Amazon（PA-API 5.0）"
    regions = "跨境"
    availability = "官方 API（已配置 AWS Key + 联盟 PartnerTag）"
    supports_search = True
    default_category = "All"
    credential_keys = ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG")
    rate_limit_sec = 1.0

    def rank_categories(self) -> List[str]:
        return ["All", "Electronics", "Home", "Beauty", "Fashion", "Toys", "Sports"]

    def _call_search(self, keyword: str, page: int, page_size: int) -> List[Product]:
        access_key, secret_key, partner_tag = self._get_credentials()
        partner_type = os.environ.get("AMAZON_PARTNER_TYPE", "Associates")
        region = os.environ.get("AMAZON_REGION", "us-east-1")
        host = os.environ.get("AMAZON_HOST", _REGION_HOST.get(region, "webservices.amazon.com"))
        uri = "/paapi5/searchitems"

        payload = {
            "Keywords": keyword,
            "SearchIndex": "All",
            "ItemCount": min(page_size, 10),
            "Resources": _RESOURCES,
            "PartnerTag": partner_tag,
            "PartnerType": partner_type,
        }
        extra = {
            "host": host,
            "x-amz-target": _TARGET,
        }
        signed = aws_sigv4_headers(
            access_key, secret_key, region, _SERVICE, host, uri, payload,
            method="POST", extra_headers=extra,
        )
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "x-amz-target": _TARGET,
            **signed,
        }
        text = post_json(f"https://{host}{uri}", payload, headers=headers)
        resp = _loads(text, self.display_name)
        if resp.get("Errors"):
            err = resp["Errors"][0]
            raise CollectorError(f"Amazon 错误 {err.get('Code')}: {err.get('Message')}")
        result = resp.get("SearchResult") or {}
        rows = result.get("Items") or []
        return self._parse_items(rows, keyword, page_size)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_search(category or self.default_category, 1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        return self._call_search(keyword, 1, min(limit, 100))

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, item in enumerate(rows[:limit], start=1):
            asin = str(item.get("ASIN") or "")
            if not asin:
                continue
            item_info = item.get("ItemInfo") or {}
            title = clean_text(((item_info.get("Title") or {}).get("DisplayValue")) or "未命名商品")
            brand = clean_text(((item_info.get("ByLineInfo") or {}).get("Brand") or {}).get("DisplayValue"))
            offers = item.get("Offers") or {}
            listings = offers.get("Listings") or []
            price = None
            currency = None
            if listings and isinstance(listings[0], dict):
                p = (listings[0].get("Price") or {})
                if p.get("Amount") is not None:
                    price = to_float(p.get("Amount"))
                else:
                    price = to_float(str(p.get("DisplayAmount", "")).replace("$", "").replace(",", ""))
                currency = p.get("Currency")
            images = item.get("Images") or {}
            img = ((images.get("Primary") or {}).get("Large") or {}).get("URL")
            browse = (item.get("BrowseNodeInfo") or {}).get("BrowseNodes") or []
            cat = clean_text(browse[0].get("DisplayName")) if browse and isinstance(browse[0], dict) else category
            products.append(
                Product(
                    platform="amazon_open",
                    product_id=asin,
                    title=title,
                    price=price,
                    original_price=None,
                    sales=None,
                    sales_text=None,
                    shop_name="Amazon",
                    brand=brand,
                    stock_status=None,
                    rank=rank,
                    category=cat or category,
                    url=item.get("DetailPageURL") or f"https://www.amazon.com/dp/{asin}",
                    image=img,
                )
            )
        if not products:
            raise CollectorError("Amazon 返回为空（检查 AWS Key 权限 / PartnerTag 是否有效 / 是否开通 PA-API）")
        return products


# ---------------------------------------------------------------------------
# 3) Shopee 开放平台 v2 —— 店铺商品列表 + 基础信息（店铺/竞品监控）
# ---------------------------------------------------------------------------
class ShopeeOpenAdapter(OfficialAdapter):
    """Shopee Open Platform v2：get_item_list + get_item_base_info。

    - 需 Partner ID / Partner Key + 商家授权 access_token + shop_id
    - 签名：HMAC-SHA256（见 shopee_sign）
    - 适合监控某店铺的在售商品（竞品店铺监控）
    """

    platform = "shopee_open"
    display_name = "Shopee（官方开放平台）"
    regions = "跨境"
    availability = "官方 API（已配置 PartnerKey + 授权 Token）"
    supports_search = False
    default_category = "在售商品"
    credential_keys = ("SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "SHOPEE_ACCESS_TOKEN")
    BASE = "https://partner.shopeemobile.com"
    rate_limit_sec = 1.0
    # 竞品店铺监控：可临时指定要监控的店铺 ID（不改变全局配置）
    shop_id_override: Optional[str] = None

    def rank_categories(self) -> List[str]:
        return ["在售商品"]

    def _get_shop_id(self) -> str:
        shop_id = (self.shop_id_override or "").strip() or (os.environ.get("SHOPEE_SHOP_ID", "") or "").strip()
        if not shop_id:
            raise CollectorError(
                "Shopee 店铺监控需要 shop_id：在面板「店铺监控」输入店铺 ID，"
                "或在配置中心填 SHOPEE_SHOP_ID 后重试。"
            )
        return shop_id

    def _query(self, api_path: str, params: dict) -> dict:
        partner_id, partner_key, token = self._get_credentials()
        shop_id = self._get_shop_id()
        timestamp = str(int(datetime.now().timestamp()))
        q = {
            "partner_id": partner_id,
            "timestamp": timestamp,
            "access_token": token,
            "shop_id": shop_id,
            **params,
        }
        q["sign"] = shopee_sign(partner_key, partner_id, api_path, timestamp, token, shop_id)
        text = fetch_text(self.BASE + api_path, params=q)
        resp = _loads(text, self.display_name)
        if resp.get("error"):
            raise CollectorError(f"Shopee 错误 {resp.get('error')}: {resp.get('message')}")
        return resp.get("response") or {}

    def _call_goods(self, page: int, page_size: int) -> List[Product]:
        page_size = min(page_size, 100)
        resp = self._query("/api/v2/product/get_item_list", {"offset": (page - 1) * page_size, "page_size": page_size, "item_status": "NORMAL"})
        rows = resp.get("item") or resp.get("items") or []
        ids = [str(x.get("item_id") or x.get("itemid")) for x in rows if isinstance(x, dict)]
        if not ids:
            raise CollectorError("Shopee 返回为空（检查 PartnerKey/权限与 token 是否过期）")
        items: List[Product] = []
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            detail = self._query("/api/v2/product/get_item_base_info", {"item_id_list": json.dumps(chunk, separators=(",", ":"))})
            items.extend(self._parse_items(detail.get("item") or [], "在售商品", page_size))
        if not items:
            raise CollectorError("Shopee 商品基础信息返回为空（检查接口权限）")
        return items

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_goods(1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        raise CollectorError("Shopee 官方接口无公开搜索，请用店铺商品列表监控（竞品店铺）")

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("item_id") or g.get("itemid") or "")
            if not pid:
                continue
            price = to_float(g.get("price"))
            if price is not None:
                price = round(price / 100000.0, 2)  # Shopee 价格单位：分（1 元 = 100000）
            imgs = g.get("image_url") or g.get("images") or []
            img = imgs[0] if isinstance(imgs, list) and imgs else None
            products.append(
                Product(
                    platform="shopee_open",
                    product_id=pid,
                    title=clean_text(g.get("item_name") or g.get("name") or "未命名商品"),
                    price=price,
                    original_price=None,
                    sales=to_int(g.get("sold") or g.get("sold_quantity")),
                    sales_text=f"销量 {g.get('sold')}" if g.get("sold") is not None else None,
                    shop_name=clean_text(g.get("shop_name") or "Shopee 店铺"),
                    stock_status="现货" if str(g.get("item_status", "")).upper() == "NORMAL" else None,
                    rank=rank,
                    category=category,
                    url=f"https://shopee.com/product/{g.get('shop_id', '')}/{pid}",
                    image=img,
                )
            )
        if not products:
            raise CollectorError("Shopee 商品解析为空")
        return products


# ---------------------------------------------------------------------------
# 4) AliExpress 联盟开放平台 —— aliexpress.affiliate.product.query（选品/榜单）
# ---------------------------------------------------------------------------
class AliExpressOpenAdapter(OfficialAdapter):
    """AliExpress 联盟官方 API：aliexpress.affiliate.product.query。

    - 需 AppKey / Secret（open.aliexpress.com 联盟应用）
    - 需授权 access_token（联盟推广者）
    - 签名：TOP 淘宝同款 md5(secret + 参数升序 + secret) 大写
    - 返回价格货币通常为 USD
    """

    platform = "aliexpress_open"
    display_name = "AliExpress（联盟官方 API）"
    regions = "跨境"
    availability = "官方 API（已配置 AppKey/Secret + 授权 Token）"
    supports_search = True
    default_category = "热销商品"
    credential_keys = ("ALIEXPRESS_OPEN_APP_KEY", "ALIEXPRESS_OPEN_APP_SECRET")
    BASE = "https://api-sg.aliexpress.com/rest"
    rate_limit_sec = 1.0

    def rank_categories(self) -> List[str]:
        return ["热销商品", "服饰", "美妆", "数码", "家居", "食品", "母婴"]

    def _call_search(self, keyword: str, page: int, page_size: int) -> List[Product]:
        app_key, secret = self._get_credentials()
        token = os.environ.get("ALIEXPRESS_OPEN_ACCESS_TOKEN", "")
        if not token:
            raise CollectorError(
                "AliExpress 联盟接口需要 access_token：请在开放平台应用授权（联盟推广者）后，"
                "把 token 填到 ALIEXPRESS_OPEN_ACCESS_TOKEN（接口文档 → 配置中心 → 官方开放平台凭证（跨境））。"
            )
        params = {
            "method": "aliexpress.affiliate.product.query",
            "app_key": app_key,
            "sign_method": "md5",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "format": "json",
            "v": "2.0",
            "access_token": token,
            "keywords": keyword,
            "page_no": page,
            "page_size": page_size,
            "sort": os.environ.get("ALIEXPRESS_SORT", "total_sales_des"),
            "currency": os.environ.get("ALIEXPRESS_CURRENCY", "USD"),
        }
        tracking_id = os.environ.get("ALIEXPRESS_TRACKING_ID", "")
        if tracking_id:
            params["tracking_id"] = tracking_id
        params["sign"] = md5_sign(params, secret)
        resp = _loads(fetch_text(self.BASE, params=params), self.display_name)
        node = resp.get("aliexpress_affiliate_product_query_response") or resp
        if node.get("error_response") or node.get("resp_result") and node["resp_result"].get("resp_code") != "200":
            err = node.get("error_response") or node.get("resp_result")
            raise CollectorError(f"AliExpress 错误: {err}")
        rows = node.get("products") or []
        if isinstance(rows, dict):
            rows = rows.get("product") or rows.get("products") or []
        return self._parse_items(rows, keyword, page_size)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_search(category or self.default_category, 1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        return self._call_search(keyword, 1, min(limit, 100))

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("product_id") or "")
            if not pid:
                continue
            price = to_float(g.get("app_sale_price") or g.get("target_sale_price") or g.get("sale_price"))
            currency = g.get("sale_price_currency") or g.get("target_sale_price_currency") or "USD"
            products.append(
                Product(
                    platform="aliexpress_open",
                    product_id=pid,
                    title=clean_text(g.get("product_title") or g.get("title") or "未命名商品"),
                    price=price,
                    original_price=to_float(g.get("target_app_sale_price") or g.get("original_price")),
                    sales=to_int(g.get("sale_orders") or g.get("sales")),
                    sales_text=f"销量 {g.get('sale_orders')}" if g.get("sale_orders") is not None else None,
                    shop_name=clean_text(g.get("shop_name") or g.get("seller_name") or "AliExpress"),
                    stock_status=None,
                    rank=rank,
                    category=clean_text(g.get("first_level_category_name") or g.get("second_level_category_name")) or category,
                    url=g.get("product_detail_url") or f"https://www.aliexpress.com/item/{pid}.html",
                    image=g.get("product_main_image_url") or g.get("image_url"),
                )
            )
        if not products:
            raise CollectorError("AliExpress 返回为空（检查 AppKey/Secret 权限与 token 是否过期）")
        return products


_ALL: List[type] = [
    TikTokShopAdapter,
    AmazonOpenAdapter,
    ShopeeOpenAdapter,
    AliExpressOpenAdapter,
]


def all_official_global_adapters() -> List[OfficialAdapter]:
    return [cls() for cls in _ALL]
