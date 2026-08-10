# -*- coding: utf-8 -*-
"""日报 + 监控历史排名快照测试。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture()
def fake_uumit(monkeypatch):
    """把 uumit_data 的联网函数替换为固定返回。"""
    import shopmonitor.uumit_data as ud

    def _ov():
        return {"order_count": 382287, "user_count": 92404, "total_amount": 656083534.77,
                "avg_order_amount": 1716.21, "total_quantity": 477910, "delivered_rate": 0.5993,
                "product_count": 1000, "category_count": 5, "brand_count": 15,
                "avg_fulfillment_time": 46.0}

    def _pf():
        return {"items": [
            {"platform": "淘宝", "product_count": 55196, "avg_price": 362.83,
             "sales_count": 621092040, "avg_rating": None},
            {"platform": "京东", "product_count": 12474, "avg_price": 2765.15,
             "sales_count": 2412529932, "avg_rating": 4.55},
        ]}

    def _hot():
        return {"items": [{"rank": 1, "title": "今日立秋", "hot": 11381248}]}

    def _baidu(type_="realtime"):
        return {"items": [{"rank": 1, "title": "各美其美 美美与共", "index": "7903980"}]}

    monkeypatch.setattr(ud, "market_overview", _ov)
    monkeypatch.setattr(ud, "platform_performance", _pf)
    monkeypatch.setattr(ud, "douyin_hot", _hot)
    monkeypatch.setattr(ud, "baidu_hot", _baidu)
    return ud


def test_build_daily_report_sections(fake_uumit):
    from shopmonitor.daily_report import build_daily_report
    md = build_daily_report()
    assert "# 电商监控日报" in md
    assert "一、监控概况" in md
    assert "二、电商大盘" in md
    assert "三、热搜" in md
    assert "四、今日告警明细" in md
    assert "五、关注商品快照" in md
    assert "今日立秋" in md
    assert "各美其美 美美与共" in md
    assert "淘宝" in md and "京东" in md


def test_build_period_report(fake_uumit):
    from shopmonitor.daily_report import build_period_report, period_report_path
    md = build_period_report("week")
    assert "电商监控周报" in md and "告警统计" in md
    md2 = build_period_report("month")
    assert "电商监控月报" in md2
    p = period_report_path("week")
    assert p.name.startswith("周报-")


def test_period_report_api(fake_uumit):
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.post("/api/v1/监控/周期报告?period=week")
    assert r.status_code == 200
    v = c.get("/api/v1/监控/周期报告?period=week")
    assert v.status_code == 200 and "电商监控周报" in v.text


def test_generate_daily_report_idempotent(fake_uumit):
    from shopmonitor.daily_report import generate_daily_report, maybe_generate_daily_report, today_report_path
    r1 = generate_daily_report(push=False)
    assert r1["date"] == today_report_path().stem
    assert today_report_path().exists()
    # 已生成 -> 幂等跳过
    assert maybe_generate_daily_report(push=False) is None


def test_daily_report_degrade_when_uumit_down(monkeypatch):
    import shopmonitor.uumit_data as ud
    def boom(*a, **k):
        raise RuntimeError("网络不通")
    monkeypatch.setattr(ud, "market_overview", boom)
    monkeypatch.setattr(ud, "platform_performance", boom)
    monkeypatch.setattr(ud, "douyin_hot", boom)
    monkeypatch.setattr(ud, "baidu_hot", boom)
    from shopmonitor.daily_report import build_daily_report
    md = build_daily_report()
    assert "UUMit 数据暂不可用" in md


def test_cache_monitor_history_roundtrip():
    from shopmonitor import cache
    cache.init_db()
    wid = cache.add_watch(platform="mock", mode="keyword", keyword="数码", top_n=10)
    cache.add_monitor_history(wid, "SKU-1", "商品甲", rank=3, price=99.0, sales=100, rating=4.5, review_count=10)
    cache.add_monitor_history(wid, "SKU-1", "商品甲", rank=2, price=89.0, sales=150, rating=4.6, review_count=20)
    cache.add_monitor_history(wid, "SKU-2", "商品乙", rank=1, price=199.0, sales=50, rating=None, review_count=None)
    recs = cache.get_monitor_history(wid)
    assert len(recs) == 3
    sku1 = [r for r in recs if r["product_id"] == "SKU-1"]
    assert sku1[0]["rank"] == 3 and sku1[1]["rank"] == 2
    prods = cache.list_monitor_products(wid)
    assert len(prods) == 2
    cache.delete_watch(wid)
