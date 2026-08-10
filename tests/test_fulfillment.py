# -*- coding: utf-8 -*-
"""运营/发货模式预设 + 履约费/仓储费/收付费/汇损/打包费 测试（离线，汇率用内置快照）。"""
import pytest

from shopmonitor import currencies as cur
from shopmonitor.fulfillment import (
    CATEGORY_PRESETS,
    FBA_FULFILLMENT_TIERS,
    FULL_TEMPLATES,
    FULFILLMENT_MODES,
    get_category_preset,
    get_full_template,
    get_fulfillment_modes,
    get_mode,
)
from shopmonitor.insights import estimate_profit


@pytest.fixture()
def fx_offline(monkeypatch):
    monkeypatch.setattr(cur, "get_rates", lambda force=False: {
        "rates": dict(cur.DEFAULT_RATES), "source": "测试快照", "updated": cur.DEFAULT_AS_OF})


def test_modes_include_amazon_fba_fbm():
    modes = {m["key"]: m for m in FULFILLMENT_MODES}
    assert "amazon_fba" in modes and "amazon_fbm" in modes
    assert modes["amazon_fba"]["platform"] == "amazon_open"
    assert modes["amazon_fba"]["fulfillment_fee"] > 0      # FBA 有履约费
    assert modes["amazon_fbm"]["fulfillment_fee"] == 0     # FBM 无履约费
    assert get_mode("amazon_fba")["name"].startswith("Amazon FBA")
    assert len(get_fulfillment_modes("amazon_open")) >= 2
    assert len(get_fulfillment_modes("tiktok_shop")) == 3


def test_estimate_profit_fba_style(fx_offline):
    usd = cur.DEFAULT_RATES["USD"]
    d = estimate_profit(
        sale_price=19.99, cost=40, shipping=8, commission_rate=0.15, other_rate=0.0,
        tax_rate=0.0, quantity=1, currency="USD",
        fulfillment="Amazon FBA", fulfillment_fee=5.5, storage_fee=0.75,
        payment_fee_rate=0.005, fx_loss_rate=0.005, packaging_fee=1.0,
    )
    assert d["fulfillment"] == "Amazon FBA"
    assert d["fulfillment_fee"] == 5.5
    assert d["storage_fee"] == 0.75
    assert d["payment_fee"] == pytest.approx(19.99 * 0.005, abs=0.001)
    sale_cny = 19.99 * usd
    fees_cny = (19.99 * 0.15 + 5.5 + 0.75) * usd + 19.99 * 0.005 * usd
    cost_cny = (40 + 8 + 1.0)
    fx_loss = sale_cny * 0.005
    assert d["total_cost"] == pytest.approx(cost_cny + fees_cny + fx_loss, abs=0.2)
    assert d["gross_profit"] == pytest.approx(sale_cny - d["total_cost"], abs=0.2)
    assert d["packaging_fee"] == 1.0
    assert d["fx_loss"] == pytest.approx(fx_loss, abs=0.05)


def test_estimate_profit_fbm_no_fulfillment(fx_offline):
    d = estimate_profit(sale_price=19.99, cost=40, shipping=12, commission_rate=0.15,
                        other_rate=0.01, tax_rate=0.0, quantity=1, currency="USD",
                        fulfillment="Amazon FBM", fulfillment_fee=0, storage_fee=0)
    assert d["fulfillment_fee"] == 0 and d["storage_fee"] == 0
    # FBM 运费更高但无履约费/仓储费 -> 对比 FBA 示例利润应不同（此处只验证结构）
    assert d["total_cost"] > 0 and d["gross_profit"] < d["sale_total_cny"]


def test_full_templates():
    keys = {x["key"] for x in FULL_TEMPLATES}
    assert "amazon_fba_small" in keys and "amazon_fba_oversize" in keys and "amazon_fbm" in keys
    t = get_full_template("amazon_fba_small")
    assert t["mode"] == "amazon_fba" and t["currency"] == "USD"
    assert t["tier"] == "large_standard_1lb" and t["acos_rate"] > 0
    assert t["return_rate"] == 0.05 and t["payment_fee_rate"] > 0


def test_modes_have_duty_return():
    fba = get_mode("amazon_fba")
    assert fba["duty_rate"] == 0.0
    assert fba["return_rate"] == 0.05       # Amazon 退货率默认 5%
    assert get_mode("pdd_dropship")["return_rate"] == 0.02  # 国内 2%
    assert get_mode("shopee_sls")["return_rate"] == 0.03


def test_estimate_profit_duty_return_fixed(fx_offline):
    usd = cur.DEFAULT_RATES["USD"]
    d = estimate_profit(
        sale_price=29.99, cost=40, shipping=8, commission_rate=0.15, other_rate=0.0,
        tax_rate=0.0, quantity=2, currency="USD",
        fulfillment="Amazon FBA", fulfillment_fee=5.5, storage_fee=0.75,
        long_storage_fee=0.15, removal_fee=0.55,
        payment_fee_rate=0.005, fx_loss_rate=0.005, packaging_fee=1.0,
        acos_rate=0.15, duty_rate=0.08, return_rate=0.05, fixed_fee=39.99,
    )
    assert d["duty_rate"] == 0.08 and d["return_rate"] == 0.05
    sale_cny = 29.99 * 2 * usd
    cost_cny = (40 + 8 + 1.0) * 2
    assert d["duty"] == pytest.approx(cost_cny * 0.08, abs=0.05)
    assert d["return_cost"] == pytest.approx(sale_cny * 0.05, abs=0.05)
    assert d["fixed_fee"] == pytest.approx(39.99 * usd, abs=0.05)
    assert d["total_cost"] == pytest.approx(
        cost_cny + d["fees_cny"] + sale_cny * 0.15 + sale_cny * 0.005 + cost_cny * 0.08 + sale_cny * 0.05 + 39.99 * usd, abs=0.5)


def test_category_presets():
    keys = {c["key"] for c in CATEGORY_PRESETS}
    assert "apparel" in keys and "digital" in keys
    assert get_category_preset("digital")["acos_rate"] > 0
    by = {c["key"]: c for c in CATEGORY_PRESETS}
    assert by["apparel"]["acos_rate"] > by["digital"]["acos_rate"]


def test_fba_tiers():
    keys = {t["key"] for t in FBA_FULFILLMENT_TIERS}
    assert {"small_standard", "large_standard_1lb", "large_standard_2lb", "small_oversize",
            "medium_oversize", "large_oversize"} <= keys
    by = {t["key"]: t for t in FBA_FULFILLMENT_TIERS}
    assert by["small_standard"]["fee"] < by["large_oversize"]["fee"]


def test_estimate_profit_acos_long_removal(fx_offline):
    usd = cur.DEFAULT_RATES["USD"]
    d = estimate_profit(
        sale_price=29.99, cost=40, shipping=8, commission_rate=0.15, other_rate=0.0,
        tax_rate=0.0, quantity=2, currency="USD",
        fulfillment="Amazon FBA", fulfillment_fee=5.5, storage_fee=0.75,
        long_storage_fee=0.15, removal_fee=0.55,
        payment_fee_rate=0.005, fx_loss_rate=0.005, packaging_fee=1.0,
        acos_rate=0.15,
    )
    assert d["long_storage_fee"] == 0.3       # 0.15 * 2 件
    assert d["removal_fee"] == 1.1            # 0.55 * 2 件
    assert d["ad_fee"] == pytest.approx(29.99 * 2 * usd * 0.15, abs=0.2)
    assert d["ad_fee_rate"] == 0.15
    sale_cny = 29.99 * 2 * usd
    fees_cny = (29.99*2*0.15 + 5.5*2 + 0.75*2 + 0.15*2 + 0.55*2) * usd + (29.99*2*0.005) * usd
    cost_cny = (40 + 8 + 1.0) * 2
    total = cost_cny + fees_cny + sale_cny*0.005 + sale_cny*0.15
    assert d["total_cost"] == pytest.approx(total, abs=0.3)
    assert d["gross_profit"] == pytest.approx(sale_cny - total, abs=0.3)


def test_fulfillment_api(fx_offline):
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/tools/fulfillment")
    assert r.status_code == 200
    j = r.json()
    keys = {m["key"] for m in j["items"]}
    assert "amazon_fba" in keys and "amazon_fbm" in keys and "pdd_dropship" in keys
    r2 = c.get("/api/v1/tools/fulfillment", params={"platform": "amazon_open"})
    assert r2.status_code == 200
    assert len(r2.json()["items"]) >= 2
    assert "fba_tiers" in r2.json() and len(r2.json()["fba_tiers"]) >= 3
    assert "category_presets" in r2.json() and len(r2.json()["category_presets"]) >= 3
    assert "templates" in r2.json() and len(r2.json()["templates"]) >= 10


def test_profit_api_fulfillment(fx_offline):
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/tools/profit", params={
        "sale_price": 19.99, "cost": 40, "shipping": 8, "commission_rate": 0.15,
        "other_rate": 0.0, "tax_rate": 0.0, "quantity": 1, "currency": "USD",
        "fulfillment": "Amazon FBA", "fulfillment_fee": 5.5, "storage_fee": 0.75,
        "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 1.0,
        "acos_rate": 0.15, "long_storage_fee": 0.15, "removal_fee": 0.55})
    assert r.status_code == 200
    j = r.json()
    assert j["fulfillment"] == "Amazon FBA"
    assert j["fulfillment_fee"] == 5.5 and j["storage_fee"] == 0.75
    assert j["payment_fee"] > 0 and j["fx_loss"] > 0 and j["packaging_fee"] == 1.0
    assert j["long_storage_fee"] == 0.15 and j["removal_fee"] == 0.55
    assert j["ad_fee"] > 0 and j["ad_fee_rate"] == 0.15
