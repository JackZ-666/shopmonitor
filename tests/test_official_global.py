"""跨境官方开放平台适配器测试（不联网：签名/解析用固定样例，请求层用 monkeypatch 模拟官方响应）。

覆盖：
- 签名函数（TikTok HMAC-SHA256 / Shopee HMAC-SHA256 / AWS SigV4 / AliExpress 复用 TOP-MD5）
- 4 个跨境官方平台已注册
- 未配置凭证 -> CollectorError（上层自动降级演示数据）
- 各平台真实响应样例解析成统一 Product
- 请求层：凭证配齐 + 模拟官方响应 -> 正常返回商品
- API 层：无凭证 -> degraded=true 演示数据
"""
import hashlib
import hmac
import json

import pytest

from shopmonitor.collectors.base import CollectorError
from shopmonitor.collectors.official_global import (
    AliExpressOpenAdapter,
    AmazonOpenAdapter,
    ShopeeOpenAdapter,
    TikTokShopAdapter,
    aws_sigv4_headers,
    shopee_sign,
    tiktok_sign,
)
from shopmonitor.collectors.registry import get_adapter, list_platforms

GLOBAL_KEYS = {
    "tiktok_shop": ("TIKTOK_SHOP_APP_KEY", "TIKTOK_SHOP_APP_SECRET"),
    "amazon_open": ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"),
    "shopee_open": ("SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "SHOPEE_ACCESS_TOKEN"),
    "aliexpress_open": ("ALIEXPRESS_OPEN_APP_KEY", "ALIEXPRESS_OPEN_APP_SECRET"),
}

TOKEN_KEYS = {
    "tiktok_shop": ("TIKTOK_SHOP_ACCESS_TOKEN", "TIKTOK_SHOP_SHOP_CIPHER", "TIKTOK_SHOP_SHOP_ID"),
    "shopee_open": (),
    "aliexpress_open": ("ALIEXPRESS_OPEN_ACCESS_TOKEN", "ALIEXPRESS_SORT", "ALIEXPRESS_CURRENCY"),
}


# ---------------- 签名函数 ----------------
def test_tiktok_sign_matches_independent_hmac():
    app_secret = "e59af819cc"
    path = "/product/202309/products/search"
    params = {"app_key": "68xu9ks5p4i8", "timestamp": "1696909648", "version": "202309",
              "keyword": "phone", "page_no": 1, "page_size": 20}
    body = {"keyword": "phone", "page_no": 1, "page_size": 20}
    sig = tiktok_sign(app_secret, path, params, body)
    items = sorted((k, str(v)) for k, v in params.items()
                   if k not in ("app_secret", "token", "access_token", "sign") and v not in (None, ""))
    joined = "".join(f"{k}{v}" for k, v in items)
    body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    raw = f"{app_secret}{path}{joined}{body_text}{app_secret}"
    expect = hmac.new(app_secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    assert sig == expect
    # sign/access_token 不参与签名
    s2 = tiktok_sign(app_secret, path, {**params, "sign": "x", "access_token": "tok"}, body)
    assert s2 == sig


def test_shopee_sign_matches_independent_hmac():
    s = shopee_sign("partner_key", "10001", "/api/v2/product/get_item_list", "1700000000", "tok", "12345")
    base = "10001/api/v2/product/get_item_list1700000000tok12345"
    expect = hmac.new(b"partner_key", base.encode("utf-8"), hashlib.sha256).hexdigest()
    assert s == expect
    assert len(s) == 64


def test_aws_sigv4_structure_and_determinism():
    kw = {"Keywords": "phone", "ItemCount": 5, "PartnerTag": "x-20", "PartnerType": "Associates", "Resources": ["Title"]}
    h = aws_sigv4_headers("AKID", "secret", "us-east-1", "ProductAdvertisingAPIv1",
                          "webservices.amazon.com", "/paapi5/searchitems", kw)
    auth = h["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKID/")
    assert "SignedHeaders=content-type;host;x-amz-date" in auth
    assert len(auth.split("Signature=")[1]) == 64
    assert h["X-Amz-Date"].endswith("Z")
    # 再次生成（同秒内应一致）
    h2 = aws_sigv4_headers("AKID", "secret", "us-east-1", "ProductAdvertisingAPIv1",
                           "webservices.amazon.com", "/paapi5/searchitems", kw)
    assert h == h2


def test_all_global_registered():
    plats = {p["platform"] for p in list_platforms()}
    for k in GLOBAL_KEYS:
        assert k in plats, k


# ---------------- 凭证状态 ----------------
@pytest.mark.parametrize("platform,keys", list(GLOBAL_KEYS.items()))
def test_not_configured_raises(monkeypatch, platform, keys):
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    for tk in TOKEN_KEYS.get(platform, ()):
        monkeypatch.delenv(tk, raising=False)
    a = get_adapter(platform)
    assert a.is_configured() is False
    with pytest.raises(CollectorError):
        a.fetch_rank(limit=3)


@pytest.mark.parametrize("platform,keys", list(GLOBAL_KEYS.items()))
def test_configured_flag(monkeypatch, platform, keys):
    for k in keys:
        monkeypatch.setenv(k, "test-value")
    assert get_adapter(platform).is_configured() is True


# ---------------- 纯解析（真实响应样例，不联网） ----------------
def test_tiktok_parse():
    rows = [
        {"id": "17350001", "name": "TikTok 爆款", "status": "ACTIVE",
         "skus": [{"price": 1999}], "sales": 5000},
        {"id": "17350002", "name": "下架商品", "status": "INACTIVE"},
    ]
    items = TikTokShopAdapter._parse_items(rows, "服饰", 10)
    assert len(items) == 2
    assert items[0].product_id == "17350001"
    assert items[0].price == 19.99  # 分 -> 元
    assert items[0].sales == 5000
    assert items[0].stock_status == "现货"
    assert items[1].stock_status is None


def test_amazon_parse():
    rows = [
        {"ASIN": "B0TEST1", "DetailPageURL": "https://www.amazon.com/dp/B0TEST1",
         "ItemInfo": {"Title": {"DisplayValue": "Amazon 爆款"},
                      "ByLineInfo": {"Brand": {"DisplayValue": "BrandX"}}},
         "Offers": {"Listings": [{"Price": {"Amount": 29.99, "Currency": "USD", "DisplayAmount": "$29.99"}}]},
         "Images": {"Primary": {"Large": {"URL": "http://img/a.jpg"}}},
         "BrowseNodeInfo": {"BrowseNodes": [{"DisplayName": "Electronics"}]}},
    ]
    items = AmazonOpenAdapter._parse_items(rows, "All", 10)
    assert items[0].product_id == "B0TEST1"
    assert items[0].price == 29.99
    assert items[0].brand == "BrandX"
    assert items[0].category == "Electronics"


def test_shopee_parse():
    rows = [
        {"item_id": 10001, "item_name": "Shopee 爆款", "price": 2990000, "sold": 120,
         "image_url": ["http://img/s.jpg"], "item_status": "NORMAL", "shop_id": 88},
    ]
    items = ShopeeOpenAdapter._parse_items(rows, "在售商品", 10)
    assert items[0].product_id == "10001"
    assert items[0].price == 29.9  # 分(1元=100000) -> 元
    assert items[0].sales == 120
    assert items[0].stock_status == "现货"


def test_aliexpress_parse():
    rows = [
        {"product_id": "1005001", "product_title": "AliExpress 爆款", "app_sale_price": "12.99",
         "sale_price_currency": "USD", "sale_orders": 999, "shop_name": "Global Store",
         "product_detail_url": "https://www.aliexpress.com/item/1005001.html",
         "product_main_image_url": "http://img/a.jpg"},
    ]
    items = AliExpressOpenAdapter._parse_items(rows, "热销商品", 10)
    assert items[0].product_id == "1005001"
    assert items[0].price == 12.99
    assert items[0].sales == 999
    assert items[0].shop_name == "Global Store"


# ---------------- 请求层：凭证齐 + 模拟官方响应 ----------------
def test_tiktok_live(monkeypatch):
    import shopmonitor.collectors.official_global as og
    monkeypatch.setenv("TIKTOK_SHOP_APP_KEY", "app")
    monkeypatch.setenv("TIKTOK_SHOP_APP_SECRET", "sec")
    monkeypatch.setenv("TIKTOK_SHOP_ACCESS_TOKEN", "tok")
    calls = []
    resp = {"code": 0, "message": "success", "data": {"products": [
        {"id": "1", "name": "TikTok 商品", "status": "ACTIVE", "skus": [{"price": 9900}]}]}}

    def fake_post(url, payload, headers=None, timeout=None):
        calls.append((url, payload, headers or {}))
        return json.dumps(resp, ensure_ascii=False)

    monkeypatch.setattr(og, "post_json", fake_post)
    items = TikTokShopAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "1"
    assert items[0].price == 99.0
    url, payload, headers = calls[0]
    assert "/product/202309/products/search" in url
    assert "sign=" in url
    assert payload["keyword"]
    assert headers.get("x-tts-access-token") == "tok"


def test_amazon_live(monkeypatch):
    import shopmonitor.collectors.official_global as og
    monkeypatch.setenv("AMAZON_ACCESS_KEY", "ak")
    monkeypatch.setenv("AMAZON_SECRET_KEY", "sk")
    monkeypatch.setenv("AMAZON_PARTNER_TAG", "tag-20")
    calls = []
    resp = {"SearchResult": {"Items": [
        {"ASIN": "B0LIVE", "ItemInfo": {"Title": {"DisplayValue": "Amazon 商品"}},
         "Offers": {"Listings": [{"Price": {"Amount": 49.99, "Currency": "USD"}}]}}]}}

    def fake_post(url, payload, headers=None, timeout=None):
        calls.append((url, payload, headers or {}))
        return json.dumps(resp, ensure_ascii=False)

    monkeypatch.setattr(og, "post_json", fake_post)
    items = AmazonOpenAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "B0LIVE"
    assert items[0].price == 49.99
    url, payload, headers = calls[0]
    assert url.endswith("/paapi5/searchitems")
    assert payload["PartnerTag"] == "tag-20"
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256")
    assert headers["x-amz-target"] == "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"


def test_shopee_live(monkeypatch):
    import shopmonitor.collectors.official_global as og
    monkeypatch.setenv("SHOPEE_PARTNER_ID", "10001")
    monkeypatch.setenv("SHOPEE_PARTNER_KEY", "pk")
    monkeypatch.setenv("SHOPEE_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("SHOPEE_SHOP_ID", "12345")
    calls = []

    def fake_fetch(url, params=None, headers=None, cookies=None, timeout=None, retries=2):
        calls.append((url, dict(params or {})))
        if "/get_item_list" in url:
            return json.dumps({"error": "", "response": {"item": [{"item_id": 777, "item_status": "NORMAL"}]}}, ensure_ascii=False)
        return json.dumps({"error": "", "response": {"item": [
            {"item_id": 777, "item_name": "Shopee 商品", "price": 1990000, "sold": 66, "item_status": "NORMAL"}]}}, ensure_ascii=False)

    monkeypatch.setattr(og, "fetch_text", fake_fetch)
    items = ShopeeOpenAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "777"
    assert items[0].price == 19.9
    assert items[0].sales == 66
    url0, q0 = calls[0]
    assert url0.endswith("/api/v2/product/get_item_list")
    assert q0["sign"] and q0["partner_id"] == "10001" and q0["shop_id"] == "12345"
    url1, q1 = calls[1]
    assert url1.endswith("/api/v2/product/get_item_base_info")
    assert "777" in q1["item_id_list"]


def test_aliexpress_requires_token(monkeypatch):
    monkeypatch.setenv("ALIEXPRESS_OPEN_APP_KEY", "app")
    monkeypatch.setenv("ALIEXPRESS_OPEN_APP_SECRET", "sec")
    monkeypatch.delenv("ALIEXPRESS_OPEN_ACCESS_TOKEN", raising=False)
    with pytest.raises(CollectorError):
        AliExpressOpenAdapter().fetch_rank(limit=3)


def test_shopee_shop_id_override(monkeypatch):
    import shopmonitor.collectors.official_global as og
    monkeypatch.setenv("SHOPEE_PARTNER_ID", "10001")
    monkeypatch.setenv("SHOPEE_PARTNER_KEY", "pk")
    monkeypatch.setenv("SHOPEE_ACCESS_TOKEN", "tok")
    monkeypatch.delenv("SHOPEE_SHOP_ID", raising=False)
    calls = []

    def fake_fetch(url, params=None, headers=None, cookies=None, timeout=None, retries=2):
        calls.append((url, dict(params or {})))
        if "/get_item_list" in url:
            return json.dumps({"error": "", "response": {"item": [{"item_id": 777}]}})
        return json.dumps({"error": "", "response": {"item": [
            {"item_id": 777, "item_name": "店铺商品", "price": 1990000, "item_status": "NORMAL"}]}})

    monkeypatch.setattr(og, "fetch_text", fake_fetch)
    a = og.ShopeeOpenAdapter()
    a.shop_id_override = "99999"   # 竞品店铺监控：临时指定店铺
    items = a.fetch_rank(limit=5)
    assert items[0].product_id == "777"
    url0, q0 = calls[0]
    assert q0["shop_id"] == "99999"


def test_aliexpress_live(monkeypatch):
    import shopmonitor.collectors.official_global as og
    monkeypatch.setenv("ALIEXPRESS_OPEN_APP_KEY", "app")
    monkeypatch.setenv("ALIEXPRESS_OPEN_APP_SECRET", "sec")
    monkeypatch.setenv("ALIEXPRESS_OPEN_ACCESS_TOKEN", "tok")
    calls = []
    resp = {"aliexpress_affiliate_product_query_response": {"current_record_count": 1, "products": [
        {"product_id": "1005002", "product_title": "AliExpress 商品", "app_sale_price": "8.88",
         "sale_price_currency": "USD", "sale_orders": 321, "shop_name": "Store"}]}}

    def fake_fetch(url, params=None, headers=None, cookies=None, timeout=None, retries=2):
        calls.append((url, dict(params or {})))
        return json.dumps(resp, ensure_ascii=False)

    monkeypatch.setattr(og, "fetch_text", fake_fetch)
    items = AliExpressOpenAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "1005002"
    assert items[0].price == 8.88
    url, params = calls[0]
    assert params["method"] == "aliexpress.affiliate.product.query"
    assert params["sign"]
    assert params["access_token"] == "tok"


# ---------------- API 层：无凭证自动降级演示数据 ----------------
def test_api_global_platforms_degrade_to_mock():
    from fastapi.testclient import TestClient

    from shopmonitor.api.main import app

    c = TestClient(app)
    for platform in GLOBAL_KEYS:
        r = c.get(f"/api/v1/rank/{platform}?limit=3")
        assert r.status_code == 200, (platform, r.text[:200])
        j = r.json()
        assert j["degraded"] is True, platform
        assert j["source"] == "mock", platform
        assert len(j["items"]) == 3, platform
