# -*- coding: utf-8 -*-
"""选品工具测试：毛利估算 / 目标价告警 / 今日变动榜。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shopmonitor import cache
from shopmonitor.insights import estimate_profit
from shopmonitor.monitor import Monitor


def test_estimate_profit_basic():
    d = estimate_profit(sale_price=129, cost=50, shipping=10, commission_rate=0.05, other_rate=0.01)
    assert d["sale_total"] == 129
    assert d["commission"] == 6.45      # 129*0.05
    assert d["other_fee"] == 1.29       # 129*0.01
    assert d["total_cost"] == round(60 + 6.45 + 1.29, 2)  # 67.74
    assert d["gross_profit"] == round(129 - 67.74, 2)     # 61.26
    assert abs(d["gross_margin"] - 61.26 / 129 * 100) < 0.01
    assert d["roi"] > 0


def test_estimate_profit_negative_case():
    d = estimate_profit(sale_price=30, cost=50, shipping=10)
    assert d["gross_profit"] < 0
    assert d["gross_margin"] < 0
def test_filter_export_and_overview():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    # xlsx 导出
    r = c.get("/api/v1/tools/filter", params={
        "platform": "mock", "category": "数码", "fmt": "xlsx", "limit": 5,
        "profit_cost_rate": 0.4, "profit_shipping": 8, "profit_acos": 0.1,
        "profit_duty_rate": 0.05, "profit_return_rate": 0.03})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    # md 导出
    md = c.get("/api/v1/tools/filter", params={
        "platform": "mock", "category": "数码", "fmt": "md", "limit": 3,
        "profit_cost_rate": 0.4, "profit_shipping": 8, "profit_acos": 0.1}).text
    assert "选品毛利表" in md and "预估毛利" in md
    # 毛利概览
    ov = c.get("/api/v1/tools/profit-overview").json()
    assert ov["count"] >= 1
    assert "total_profit" in ov and "positive_ratio" in ov
    assert ov["items"] and ov["items"][0]["estimated_profit"] is not None


def test_rank_snapshot_trend():
    from datetime import date, timedelta
    import json
    cache.init_db()
    c = cache._conn()
    today = date.today().isoformat()
    yest = (date.today() - timedelta(days=1)).isoformat()
    for d, ids in ((yest, ["a", "b", "c"]), (today, ["a", "b", "c", "d"])):
        c.execute("INSERT OR REPLACE INTO rank_snapshots(platform, category, captured_date, payload) VALUES(?,?,?,?)",
                  ("mock", "数码", d, json.dumps({"count": len(ids), "avg_price": 10.0, "ids": ids})))
    c.commit()
    c.close()
    tr = cache.rank_snapshot_trend("mock", "数码", 7)
    assert len(tr["items"]) == 2
    assert tr["items"][-1]["new_count"] == 1  # 新增 d
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    r = TestClient(app).get("/api/v1/工具/榜单趋势", params={"platform": "mock", "category": "数码", "days": 7})
    assert r.status_code == 200 and len(r.json()["items"]) == 2


def test_shop_monitor_and_source_guide(monkeypatch):
    for k in ("SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "SHOPEE_ACCESS_TOKEN", "SHOPEE_SHOP_ID",
              "ALIBABA_APP_KEY", "ALIBABA_APP_SECRET", "ALIBABA_ACCESS_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/工具/店铺监控", params={"platform": "shopee_open", "shop_id": "123"})
    j = r.json()
    assert j["ok"] is False and "凭证" in j["message"]
    r2 = c.get("/api/v1/工具/找货源", params={"keyword": "无线耳机"})
    j2 = r2.json()
    assert j2["ok"] is False and "凭证" in j2["message"]


def test_price_bands_and_product_est():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/工具/价格带分析", params={"platform": "mock", "category": "数码"})
    assert r.status_code == 200
    j = r.json()
    assert j["total"] >= 1 and len(j["bands"]) >= 5
    assert sum(b["count"] for b in j["bands"]) == j["total"]
    assert "suggestion" in j
    # 商品详情带预估毛利
    c.get("/api/v1/rank/mock?category=数码&limit=2&fresh=true")
    pid = c.get("/api/v1/rank/mock?category=数码&limit=2").json()["items"][0]["product_id"]
    d = c.get(f"/api/v1/商品/mock/{pid}").json()
    assert d["estimated_profit"] is not None
    assert d["estimated_margin"] is not None
    assert d["estimated_params"]["cost_rate"] == 0.4
    assert d["estimated_monthly_sales"] is not None
    assert d["estimated_gmv"] is not None and d["estimated_gmv"] > 0
    # 跨平台价格带对比
    cmp = c.get("/api/v1/工具/跨平台价格带", params={"category": "数码", "platforms": "jd,taobao,mock"}).json()
    assert cmp["count"] >= 2
    assert all("platform" in x for x in cmp["items"])


def test_competition_and_shop_dynamics():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/工具/竞争度分析", params={"platform": "mock", "category": "数码"})
    assert r.status_code == 200
    j = r.json()
    assert j["total"] >= 1 and j["seller_count"] >= 1
    assert "score" in j and j["level"] in ("蓝海", "中等竞争", "红海")
    assert len(j["top_sellers"]) >= 1
    d = c.get("/api/v1/工具/竞品动态", params={"days": 7})
    assert d.status_code == 200
    assert "events" in d.json() and "note" in d.json()


def test_compare_report_with_profit():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    j = c.get("/api/v1/rank/mock?category=数码&limit=2&fresh=true").json()
    ids = ",".join(i["product_id"] for i in j["items"])
    r = c.get("/api/v1/report/compare", params={
        "platform": "mock", "product_ids": ids, "fmt": "json",
        "profit_cost_rate": 0.4, "profit_shipping": 8, "profit_acos": 0.1})
    assert r.status_code == 200
    rows = r.json()
    assert rows and rows[0]["estimated_profit"] is not None
    assert rows[0]["estimated_margin"] is not None
    md = c.get("/api/v1/report/compare", params={
        "platform": "mock", "product_ids": ids, "fmt": "md",
        "profit_cost_rate": 0.4, "profit_shipping": 8, "profit_acos": 0.1}).text
    assert "预估毛利" in md and "毛利率" in md


def test_filter_estimated_profit():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/工具/筛选", params={
        "platform": "mock", "category": "数码", "limit": 10,
        "profit_cost_rate": 0.4, "profit_shipping": 8, "profit_acos": 0.1,
        "profit_min": 1})
    assert r.status_code == 200
    j = r.json()
    assert j["count"] >= 1
    pr = j["estimated_profit_params"]
    assert pr["cost_rate"] == 0.4 and pr["shipping"] == 8 and pr["acos"] == 0.1
    for it in j["items"]:
        assert it["estimated_profit"] is not None
        assert it["estimated_profit"] >= 1  # profit_min 过滤生效
        assert it["estimated_margin"] is not None
    # 未传参数时默认 0.4/0/0，也能算出预估毛利
    r2 = c.get("/api/v1/工具/筛选", params={"platform": "mock", "category": "数码", "limit": 5})
    j2 = r2.json()
    assert j2["items"] and j2["items"][0]["estimated_profit"] is not None
def test_estimate_profit_with_tax_and_quantity():
    d = estimate_profit(sale_price=129, cost=50, shipping=10,
                        commission_rate=0.05, other_rate=0.01, tax_rate=0.13, quantity=2)
    assert d["quantity"] == 2
    assert d["sale_total"] == 258          # 129*2
    assert d["commission"] == round(129 * 0.05 * 2, 2)   # 12.9
    assert d["other_fee"] == round(129 * 0.01 * 2, 2)    # 2.58
    assert d["tax"] == round(129 * 0.13 * 2, 2)          # 33.54
    assert d["total_cost"] == round((50 + 10) * 2 + 12.9 + 2.58 + 33.54, 2)  # 169.02
    assert d["gross_profit"] == round(258 - 169.02, 2)   # 88.98
    assert d["gross_margin"] > 0 and d["roi"] > 0


def test_watch_target_price_roundtrip():
    cache.init_db()
    wid = cache.add_watch(platform="mock", mode="keyword", keyword="数码", top_n=5, target_price=99.0)
    w = cache.get_watch(wid)
    assert w["target_price"] == 99.0
    cache.delete_watch(wid)


def test_monitor_target_price_alert():
    cache.init_db()
    wid = cache.add_watch(platform="mock", mode="product", product_id="P1", target_price=100.0)
    w = cache.get_watch(wid)

    class FakeItem:
        product_id = "P1"
        title = "测试商品"
        price = 88.0
        sales = 10
        rating = 4.5
        review_count = 5
        rank = 2
        stock_status = "现货"

    m = Monitor()
    state = {"last_price": 120.0, "last_sales": 5, "last_rating": 4.5, "last_review_count": 5,
             "last_stock": "现货", "last_rank": 2}
    alerts = m._compare(w, FakeItem(), state)
    types = [a["alert_type"] for a in alerts]
    assert "target_price" in types
    cache.delete_watch(wid)


def test_watch_overview():
    cache.init_db()
    wid = cache.add_watch(platform="mock", mode="keyword", keyword="数码", top_n=5, target_price=99.0)
    cache.add_monitor_history(wid, "SKU-O1", "总览商品", rank=2, price=88.0, sales=300, rating=4.5, review_count=10)
    cache.upsert_monitor_state(wid, "SKU-O1", {"last_price": 88.0, "last_sales": 300, "last_rating": 4.5,
                                                "last_review_count": 10, "last_stock": "现货", "last_rank": 2})
    rows = cache.watch_overview()
    hit = next((x for x in rows if x["product_id"] == "SKU-O1"), None)
    assert hit is not None
    assert hit["price"] == 88.0
    assert hit["rank"] == 2
    assert hit["target_price"] == 99.0
    cache.delete_watch(wid)


def test_parse_product_lines_urls():
    from shopmonitor.batch_import import parse_product_lines
    text = "\n".join([
        "https://item.jd.com/100012345.html",
        "https://www.amazon.com/dp/B0ABCDEFGH",
        "https://item.taobao.com/item.htm?id=987654321",
        "https://shopee.com.my/product/123/4567890",
        "jd:7777777",
        "未知链接 https://example.com/abc",
    ])
    out = parse_product_lines(text)
    jd = [x for x in out if x["platform"] == "jd" and x["source"] == "url"]
    assert jd and jd[0]["product_id"] == "100012345"
    # amazon
    amz = [x for x in out if x["platform"] == "amazon"]
    assert amz and amz[0]["product_id"] == "B0ABCDEFGH"
    tb = [x for x in out if x["platform"] == "taobao"]
    assert tb and tb[0]["product_id"] == "987654321"
    sp = [x for x in out if x["platform"] == "shopee"]
    assert sp and sp[0]["product_id"] == "4567890"
    expl = [x for x in out if x["source"] == "explicit"]
    assert expl and expl[0]["platform"] == "jd" and expl[0]["product_id"] == "7777777"
    bad = [x for x in out if x["source"] in ("no_platform", "unrecognized_url")]
    assert bad


def test_parse_product_lines_plain_with_default():
    from shopmonitor.batch_import import parse_product_lines
    out = parse_product_lines("ID123\nID456", default_platform="jd")
    assert len(out) == 2 and all(x["platform"] == "jd" and x["source"] == "plain" for x in out)


def test_hot_trend_multi_day():
    cache.init_db()
    from datetime import datetime, timedelta
    from shopmonitor import cache as c
    # 直接插两天数据（绕过 record_hot_snapshot 的当日限制）
    conn = c._conn()
    day1 = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    day2 = datetime.now().strftime("%Y-%m-%d")
    for word, h1, h2 in [("甲词", 100, 180), ("乙词", 200, 90)]:
        conn.execute("INSERT OR REPLACE INTO hot_history(platform, word, heat, rank, captured_at) VALUES(?,?,?,?,?)",
                     ("test_hot", word, h1, 1, day1))
        conn.execute("INSERT OR REPLACE INTO hot_history(platform, word, heat, rank, captured_at) VALUES(?,?,?,?,?)",
                     ("test_hot", word, h2, 1, day2))
    conn.commit(); conn.close()
    d = c.hot_trend("test_hot", days=7, limit=10)
    by = {x["word"]: x for x in d["items"]}
    assert by["甲词"]["change_pct"] == 80.0   # 100 -> 180
    assert by["乙词"]["change_pct"] == -55.0  # 200 -> 90
    # 按最新热度排序：甲 180 应在 乙 90 前
    assert d["items"][0]["word"] == "甲词"


def test_watch_has_state_and_new_arrivals():
    cache.init_db()
    wid = cache.add_watch(platform="mock", mode="keyword", keyword="数码", top_n=5)
    assert cache.watch_has_state(wid) is False
    cache.upsert_monitor_state(wid, "SKU-N1", {"last_price": 10.0, "last_sales": 1, "last_rating": 4.0,
                                                "last_review_count": 1, "last_stock": "现货", "last_rank": 1})
    assert cache.watch_has_state(wid) is True
    # 今天第一次出现的商品应出现在新品榜
    cache.add_monitor_history(wid, "SKU-NEW", "新品", rank=1, price=9.9, sales=1, rating=4.0, review_count=1)
    rows = cache.recent_new_arrivals(days=3, limit=10)
    hit = next((x for x in rows if x["product_id"] == "SKU-NEW"), None)
    assert hit is not None
    cache.delete_watch(wid)


def test_to_markdown_en():
    from shopmonitor.models import CompareRow
    from shopmonitor.report import to_markdown, to_csv
    rows = [CompareRow(platform="jd", product_id="1", title="耳机", price=99.0)]
    md = to_markdown(rows, lang="en")
    assert "Platform" in md and "Title" in md and "Price" in md
    csv_text = to_csv(rows, lang="en")
    assert csv_text.startswith("Platform,Product ID,Title")


def test_dashboard_report_en(monkeypatch):
    import shopmonitor.uumit_data as ud
    monkeypatch.setattr(ud, "market_overview", lambda fresh=False: {
        "order_count": 1, "user_count": 1, "total_amount": 100.0, "avg_order_amount": 100.0,
        "total_quantity": 1, "product_count": 1, "category_count": 1, "brand_count": 1, "delivered_rate": 0.5})
    monkeypatch.setattr(ud, "platform_performance", lambda fresh=False: {"items": [
        {"platform": "Taobao", "product_count": 1, "avg_price": 1.0, "sales_count": 1, "avg_rating": None}]})
    monkeypatch.setattr(ud, "sales_trend", lambda **kw: {"items": [
        {"period": "2024-01", "total_amount": 100.0, "order_count": 1, "total_quantity": 1, "avg_order_amount": 100.0}]})
    md = ud.dashboard_report(fmt="md", lang="en", fresh=True)
    assert "E-Commerce Market Dashboard" in md
    assert "Platform Comparison" in md


def test_recent_movers():
    cache.init_db()
    wid = cache.add_watch(platform="mock", mode="keyword", keyword="数码", top_n=5)
    # 三条快照：价格 120 -> 100 -> 90（降价），销量 100 -> 300（飙升）
    cache.add_monitor_history(wid, "SKU-A", "商品甲", rank=1, price=120.0, sales=100, rating=4.5, review_count=10)
    cache.add_monitor_history(wid, "SKU-A", "商品甲", rank=2, price=100.0, sales=300, rating=4.5, review_count=10)
    cache.add_monitor_history(wid, "SKU-A", "商品甲", rank=3, price=90.0, sales=500, rating=4.5, review_count=10)
    d = cache.recent_movers(limit=10)
    assert d["total_compared"] >= 1
    drop = next((x for x in d["drops"] if x["title"] == "商品甲"), None)
    assert drop is not None
    assert drop["price_change_pct"] < 0
    surge = next((x for x in d["sales_surges"] if x["title"] == "商品甲"), None)
    assert surge is not None
    assert surge["sales_delta"] == 200  # 100 -> 300
    cache.delete_watch(wid)
