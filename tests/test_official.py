"""官方开放平台适配器测试（不联网：签名/解析用固定样例，请求层用 monkeypatch 模拟官方响应）。

覆盖：
- 签名函数（MD5 / HMAC-SHA1 / 抖店 param_json 排序）
- 5 个官方平台已注册
- 未配置凭证 -> CollectorError（上层自动降级演示数据）
- 各平台真实响应样例解析成统一 Product
- 请求层：凭证配齐 + 模拟官方响应 -> 正常返回商品
- API 层：无凭证 -> degraded=true 演示数据
"""
import json

import pytest

from shopmonitor.collectors.base import CollectorError
from shopmonitor.collectors.official import (
    AlibabaOpenAdapter,
    DouyinMallAdapter,
    KuaishouOpenAdapter,
    PddOpenAdapter,
    TaobaoOpenAdapter,
    hmac_sha1_base64,
    md5_sign,
    sorted_json,
)
from shopmonitor.collectors.registry import get_adapter, list_platforms

OFFICIAL_KEYS = {
    "douyin_mall": ("DOUYIN_MALL_APP_ID", "DOUYIN_MALL_SECRET"),
    "taobao_open": ("TAOBAO_APP_KEY", "TAOBAO_APP_SECRET"),
    "pdd_open": ("PDD_CLIENT_ID", "PDD_CLIENT_SECRET"),
    "alibaba_open": ("ALIBABA_APP_KEY", "ALIBABA_APP_SECRET"),
    "kuaishou_open": ("KUAISHOU_APP_KEY", "KUAISHOU_APP_SECRET"),
}

TOKEN_KEYS = {
    "alibaba_open": "ALIBABA_ACCESS_TOKEN",
    "kuaishou_open": "KUAISHOU_ACCESS_TOKEN",
}


# ---------------- 签名工具 ----------------
def test_signatures():
    # md5(secret + "a1b2" + secret).upper()
    assert md5_sign({"a": "1", "b": "2"}, "sec") == "7AB23CC77796A2899E6C5BF5D76D230E"
    # 空值不参与
    assert md5_sign({"a": "1", "b": ""}, "sec") == md5_sign({"a": "1"}, "sec")
    # sign 字段不参与；sign_method 参与（淘宝/快手规范）
    assert md5_sign({"a": "1", "sign": "x"}, "sec") == md5_sign({"a": "1"}, "sec")
    assert md5_sign({"a": "1", "sign_method": "md5"}, "sec") != md5_sign({"a": "1"}, "sec")
    # HMAC-SHA1 base64 稳定输出
    s = hmac_sha1_base64({"a": "1"}, "sec")
    assert isinstance(s, str) and len(s) > 10
    # 抖店 param_json：key 升序、无空格
    assert sorted_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_all_official_registered():
    plats = {p["platform"] for p in list_platforms()}
    for k in OFFICIAL_KEYS:
        assert k in plats, k


# ---------------- 凭证状态 ----------------
@pytest.mark.parametrize("platform,keys", list(OFFICIAL_KEYS.items()))
def test_not_configured_raises(monkeypatch, platform, keys):
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    for tk in TOKEN_KEYS.values():
        monkeypatch.delenv(tk, raising=False)
    a = get_adapter(platform)
    assert a.is_configured() is False
    with pytest.raises(CollectorError):
        a.fetch_rank(limit=3)


@pytest.mark.parametrize("platform,keys", list(OFFICIAL_KEYS.items()))
def test_configured_flag(monkeypatch, platform, keys):
    for k in keys:
        monkeypatch.setenv(k, "test-value")
    assert get_adapter(platform).is_configured() is True


# ---------------- 纯解析（真实响应样例，不联网） ----------------
def test_douyin_parse():
    rows = [
        {"product_id": "123", "name": "爆款连衣裙", "price": 12900, "market_price": 15900,
         "img": ["http://img/a.jpg"], "status": 0, "sales": 3200, "first_cid_name": "女装"},
        {"product_id": "456", "name": "衬衫", "price": 9900, "status": 2},
    ]
    items = DouyinMallAdapter._parse_items(rows, "全部商品", 10)
    assert len(items) == 2
    assert items[0].product_id == "123"
    assert items[0].price == 129.0  # 分 -> 元
    assert items[0].sales == 3200
    assert items[0].stock_status == "现货"
    assert items[1].stock_status == "缺货"
    assert items[0].url and items[0].image


def test_taobao_parse():
    rows = [
        {"item_id": "888", "title": "无线耳机", "zk_final_price": "99.00", "reserve_price": "199.00",
         "volume": "2300", "shop_title": "耳机旗舰店", "pict_url": "http://img/x.jpg",
         "category_name": "数码", "coupon_amount": "20"},
    ]
    items = TaobaoOpenAdapter._parse_items(rows, "数码", 10)
    assert items[0].product_id == "888"
    assert items[0].price == 99.0
    assert items[0].sales == 2300
    assert items[0].promo_text == "领券立减 ¥20"
    assert items[0].is_promo is True
    assert items[0].shop_name == "耳机旗舰店"


def test_pdd_parse():
    rows = [
        {"goods_id": "777", "goods_name": "手机壳", "min_group_price": 1290,
         "min_normal_price": 1590, "sales": 45600, "mall_name": "手机壳专卖店",
         "goods_thumbnail_url": "http://img/p.jpg", "coupon_discount": 100},
    ]
    items = PddOpenAdapter._parse_items(rows, "百货", 10)
    assert items[0].product_id == "777"
    assert items[0].price == 12.9
    assert items[0].original_price == 15.9
    assert items[0].sales == 45600
    assert items[0].promo_text == "领券立减 ¥100"


def test_alibaba_parse():
    rows = [
        {"offerId": "555", "subject": "工厂直供数据线", "priceInfo": [{"price": 3.5}],
         "companyName": "深圳工厂", "image": "http://img/a.jpg"},
    ]
    items = AlibabaOpenAdapter._parse_items(rows, "数码配件", 10)
    assert items[0].product_id == "555"
    assert items[0].price == 3.5
    assert items[0].shop_name == "深圳工厂"
    assert items[0].url == "https://detail.1688.com/offer/555.html"


def test_kuaishou_parse():
    rows = [
        {"goodsId": "999", "goodsName": "快手爆款", "goodsPrice": "59.9", "sales": 1200,
         "shopName": "快手小店", "goodsImg": "http://img/k.jpg"},
    ]
    items = KuaishouOpenAdapter._parse_items(rows, "全部商品", 10)
    assert items[0].product_id == "999"
    assert items[0].price == 59.9
    assert items[0].sales == 1200


# ---------------- 请求层：凭证齐 + 模拟官方响应 ----------------
def _mock_fetch(monkeypatch, resp_text):
    import shopmonitor.collectors.official as official

    calls = []

    def fake_fetch(url, params=None, headers=None, cookies=None, timeout=None, retries=2):
        calls.append((url, dict(params or {})))
        return resp_text

    monkeypatch.setattr(official, "fetch_text", fake_fetch)
    return calls


def test_douyin_live(monkeypatch):
    monkeypatch.setenv("DOUYIN_MALL_APP_ID", "app")
    monkeypatch.setenv("DOUYIN_MALL_SECRET", "sec")
    resp = {"err_no": 0, "data": {"data": [{"product_id": "1", "name": "抖店商品", "price": 10000, "status": 0}]}}
    calls = _mock_fetch(monkeypatch, json.dumps(resp, ensure_ascii=False))
    items = DouyinMallAdapter().fetch_rank(limit=5)
    assert len(items) == 1
    assert items[0].price == 100.0
    url, params = calls[0]
    assert "product.list" in params["method"]
    assert params["sign"]


def test_taobao_live(monkeypatch):
    monkeypatch.setenv("TAOBAO_APP_KEY", "app")
    monkeypatch.setenv("TAOBAO_APP_SECRET", "sec")
    resp = {"tbk_dg_material_optional_response": {"result_list": {"map_data": [
        {"item_id": "9", "title": "淘宝商品", "zk_final_price": "19.9", "volume": "100"}]}}}
    calls = _mock_fetch(monkeypatch, json.dumps(resp, ensure_ascii=False))
    items = TaobaoOpenAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "9"
    url, params = calls[0]
    assert params["method"] == "taobao.tbk.dg.material.optional"
    assert params["sign"]


def test_pdd_live(monkeypatch):
    monkeypatch.setenv("PDD_CLIENT_ID", "cid")
    monkeypatch.setenv("PDD_CLIENT_SECRET", "sec")
    resp = {"goods_search_response": {"goods_list": [
        {"goods_id": "77", "goods_name": "拼多多商品", "min_group_price": 900, "sales": 300}]}}
    calls = _mock_fetch(monkeypatch, json.dumps(resp, ensure_ascii=False))
    items = PddOpenAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "77"
    assert items[0].price == 9.0
    url, params = calls[0]
    assert params["type"] == "pdd.ddk.goods.search"
    assert params["sign"]


def test_alibaba_requires_token(monkeypatch):
    monkeypatch.setenv("ALIBABA_APP_KEY", "app")
    monkeypatch.setenv("ALIBABA_APP_SECRET", "sec")
    monkeypatch.delenv("ALIBABA_ACCESS_TOKEN", raising=False)
    with pytest.raises(CollectorError):
        AlibabaOpenAdapter().fetch_rank(limit=3)


def test_alibaba_live(monkeypatch):
    monkeypatch.setenv("ALIBABA_APP_KEY", "app")
    monkeypatch.setenv("ALIBABA_APP_SECRET", "sec")
    monkeypatch.setenv("ALIBABA_ACCESS_TOKEN", "tok")
    resp = {"result": {"result": [
        {"offerId": "55", "subject": "1688货源", "priceInfo": [{"price": 2.5}], "companyName": "工厂"}]}}
    calls = _mock_fetch(monkeypatch, json.dumps(resp, ensure_ascii=False))
    items = AlibabaOpenAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "55"
    assert items[0].price == 2.5
    url, params = calls[0]
    assert params["access_token"] == "tok"
    assert params["_aop_signature"]


def test_kuaishou_requires_token(monkeypatch):
    monkeypatch.setenv("KUAISHOU_APP_KEY", "app")
    monkeypatch.setenv("KUAISHOU_APP_SECRET", "sec")
    monkeypatch.delenv("KUAISHOU_ACCESS_TOKEN", raising=False)
    with pytest.raises(CollectorError):
        KuaishouOpenAdapter().fetch_rank(limit=3)


def test_kuaishou_live(monkeypatch):
    monkeypatch.setenv("KUAISHOU_APP_KEY", "app")
    monkeypatch.setenv("KUAISHOU_APP_SECRET", "sec")
    monkeypatch.setenv("KUAISHOU_ACCESS_TOKEN", "tok")
    resp = {"result": 0, "data": {"goodsList": [
        {"goodsId": "99", "goodsName": "快手商品", "goodsPrice": "29.9"}]}}
    calls = _mock_fetch(monkeypatch, json.dumps(resp, ensure_ascii=False))
    items = KuaishouOpenAdapter().fetch_rank(limit=5)
    assert items[0].product_id == "99"
    assert items[0].price == 29.9
    url, params = calls[0]
    assert params["appKey"] == "app"
    assert params["sign"]


# ---------------- API 层：无凭证自动降级演示数据 ----------------
def test_api_official_platforms_degrade_to_mock():
    from fastapi.testclient import TestClient

    from shopmonitor.api.main import app

    c = TestClient(app)
    for platform in OFFICIAL_KEYS:
        r = c.get(f"/api/v1/rank/{platform}?limit=3")
        assert r.status_code == 200, (platform, r.text[:200])
        j = r.json()
        assert j["degraded"] is True, platform
        assert j["source"] == "mock", platform
        assert len(j["items"]) == 3, platform
