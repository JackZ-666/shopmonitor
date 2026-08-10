"""定时监控：关注 CRUD / 告警生成 / 已读。"""
import sys

from fastapi.testclient import TestClient

from shopmonitor.api.main import app
from shopmonitor import cache
from shopmonitor.monitor import monitor

c = TestClient(app)


def _add_watch(**kw):
    body = {"platform": "mock", "mode": "keyword", "category": "数码", "top_n": 3}
    body.update(kw)
    return c.post("/api/v1/monitor/watches", json=body).json()


def test_watch_crud():
    r = _add_watch(alias="数码榜")
    wid = r["id"]
    assert wid > 0
    lst = c.get("/api/v1/monitor/watches").json()["watches"]
    assert any(w["id"] == wid and w["enabled"] for w in lst)
    # 开关
    toggled = c.post(f"/api/v1/monitor/watches/{wid}/toggle").json()["watch"]
    assert toggled["enabled"] is False
    # 删除
    d = c.delete(f"/api/v1/monitor/watches/{wid}")
    assert d.status_code == 200
    assert not any(w["id"] == wid for w in c.get("/api/v1/monitor/watches").json()["watches"])


def test_alert_generation():
    wid = _add_watch(alias="告警测试")["id"]
    # 第一轮：建立基线（不告警）
    s1 = monitor.run_once()
    assert s1["alerts"] == 0
    # 找出榜上第一个商品当前价，把"上次价"人为调高 20 元，模拟之前更贵
    j = c.get("/api/v1/rank/mock?category=数码&limit=3&fresh=true").json()
    pid = j["items"][0]["product_id"]
    now_price = j["items"][0]["price"]
    cache.upsert_monitor_state(
        wid, pid,
        {
            "last_price": (now_price or 0) + 20,
            "last_sales": 0,
            "last_rating": 5.0,
            "last_review_count": 0,
            "last_stock": "现货",
            "last_rank": 1,
        },
    )
    s2 = monitor.run_once()
    assert s2["alerts"] >= 1
    alerts = c.get("/api/v1/monitor/alerts?unread=true").json()["alerts"]
    price_drops = [a for a in alerts if a["alert_type"] == "price_drop" and a["product_id"] == pid]
    assert price_drops, "应产生降价告警"
    # 标记已读
    marked = c.post("/api/v1/monitor/alerts/read", json={}).json()["marked"]
    assert marked >= 1
    assert c.get("/api/v1/monitor/alerts?unread=true").json()["unread"] == 0


def test_monitor_status_endpoint():
    st = c.get("/api/v1/monitor/status").json()
    assert "scheduler_running" in st
    assert "watch_count" in st
    assert "unread_alerts" in st
