# -*- coding: utf-8 -*-
"""跨境结算币种与汇率测试（不依赖网络：monkeypatch 汇率源为内置快照）。"""
import pytest

from shopmonitor import currencies as cur
from shopmonitor.insights import estimate_profit


@pytest.fixture()
def fx_offline(monkeypatch):
    """把汇率源替换为内置快照，保证离线可测且结果确定。"""
    monkeypatch.setattr(cur, "get_rates", lambda force=False: {
        "rates": dict(cur.DEFAULT_RATES), "source": "测试快照", "updated": cur.DEFAULT_AS_OF})


def test_rates_offline(fx_offline):
    d = cur.get_rates(force=True)
    assert d["rates"]["USD"] == pytest.approx(cur.DEFAULT_RATES["USD"], abs=0.01)
    assert d["source"] == "测试快照"
    assert cur.get_rate("CNY") == 1.0
    assert cur.get_rate("USD") == cur.DEFAULT_RATES["USD"]
    assert cur.get_rate("不存在的币种") == 1.0


def test_convert(fx_offline):
    usd = cur.DEFAULT_RATES["USD"]
    assert cur.convert_to_cny(100, "USD") == pytest.approx(100 * usd, rel=0.01)
    assert cur.convert_from_cny(100 * usd, "USD") == pytest.approx(100, rel=0.02)
    assert cur.symbol("USD") == "$"
    assert cur.symbol("MYR") == "RM"


def test_estimate_profit_cross_border(fx_offline):
    usd = cur.DEFAULT_RATES["USD"]
    d = estimate_profit(sale_price=19.99, cost=40, shipping=8,
                        commission_rate=0.15, other_rate=0.03, tax_rate=0.0,
                        quantity=1, currency="USD")
    assert d["currency"] == "USD"
    assert d["fx_rate"] == pytest.approx(round(usd, 4), abs=0.001)
    assert d["sale_total"] == 19.99                       # 结算币种收入
    assert d["sale_total_cny"] == pytest.approx(19.99 * usd, abs=0.05)
    assert d["commission"] == pytest.approx(19.99 * 0.15, abs=0.01)
    fees_cny = (19.99 * 0.15 + 19.99 * 0.03) * usd
    assert d["total_cost"] == pytest.approx(48 + fees_cny, abs=0.1)
    assert d["gross_profit"] == pytest.approx(d["sale_total_cny"] - d["total_cost"], abs=0.1)
    assert d["gross_profit_local"] == pytest.approx(d["gross_profit"] / usd, abs=0.05)


def test_estimate_profit_cny_still_works():
    # 人民币默认：结果与原口径一致（回归保护）
    d = estimate_profit(sale_price=129, cost=50, shipping=10, commission_rate=0.05,
                        other_rate=0.01, tax_rate=0.13, quantity=2)
    assert d["currency"] == "CNY"
    assert d["fx_rate"] == 1.0
    assert d["tax"] == 33.54 and d["total_cost"] == 169.02 and d["gross_profit"] == 88.98


def test_rates_api(fx_offline):
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/tools/rates")
    assert r.status_code == 200
    j = r.json()
    assert j["base"] == "CNY"
    assert j["rates"]["USD"] > 1
    assert "amazon_open" in j["platforms"]
    assert "tiktok_shop" in j["platforms"]
    assert j["currencies"]["USD"]["symbol"] == "$"


def test_profit_api_cross_border(fx_offline):
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/tools/profit", params={
        "sale_price": 19.99, "cost": 40, "shipping": 8,
        "commission_rate": 0.15, "other_rate": 0.03, "tax_rate": 0.0,
        "quantity": 1, "currency": "USD"})
    assert r.status_code == 200
    j = r.json()
    assert j["currency"] == "USD"
    assert j["sale_total_cny"] > j["sale_total"]
    assert "fx_rate" in j and j["fx_rate"] > 1
