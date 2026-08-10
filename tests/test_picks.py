# -*- coding: utf-8 -*-
"""选品库（收藏/备选管理）+ 蓝海选词 测试。"""
import pytest

from shopmonitor import cache


def _clean_picks():
    cache.init_db()
    for p in cache.list_picks():
        cache.delete_pick(p["id"])


def test_picks_crud():
    _clean_picks()
    pid = cache.add_pick("mock", "demo-001", "测试商品", price=99.0, status="考察中", note="先看看")
    assert pid > 0
    rows = cache.list_picks()
    assert any(x["id"] == pid and x["title"] == "测试商品" for x in rows)
    # 同平台+商品再次加入 -> 更新不重复
    pid2 = cache.add_pick("mock", "demo-001", "测试商品2", price=88.0)
    assert pid2 == pid
    rows = cache.list_picks()
    assert len(rows) == 1 and rows[0]["price"] == 88.0
    assert cache.update_pick(pid, status="已上架", note="定了") is True
    assert cache.list_picks(status="已上架")[0]["id"] == pid
    assert cache.delete_pick(pid) is True
    assert cache.list_picks() == []
    _clean_picks()


def test_picks_api():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    _clean_picks()
    r = c.post("/api/v1/选品库", json={"platform": "jd", "product_id": "1001", "title": "京东款", "price": 199})
    assert r.status_code == 200 and r.json()["id"] > 0
    lst = c.get("/api/v1/选品库").json()
    assert lst["count"] >= 1 and lst["items"][0]["platform"] == "jd"
    pid = lst["items"][0]["id"]
    u = c.patch(f"/api/v1/选品库/{pid}", json={"status": "可上架"})
    assert u.status_code == 200
    assert c.get("/api/v1/选品库", params={"status": "可上架"}).json()["count"] >= 1
    d = c.delete(f"/api/v1/选品库/{pid}")
    assert d.status_code == 200
    _clean_picks()


def test_blue_ocean(monkeypatch):
    import shopmonitor.uumit_data as ud
    monkeypatch.setattr(ud, "douyin_hot", lambda fresh=False: {"items": [
        {"rank": 1, "title": "甲词", "hot": 1000},
        {"rank": 2, "title": "乙词", "hot": 900},
    ]})
    counts = {"甲词": 2, "乙词": 20}
    monkeypatch.setattr(ud, "taobao_suggest", lambda kw, fresh=False: {"count": counts.get(kw, 5), "items": []})
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.get("/api/v1/工具/蓝海选词")
    assert r.status_code == 200
    j = r.json()
    assert j["count"] == 2
    by = {x["word"]: x for x in j["items"]}
    # 甲词联想词少 -> 蓝海指数更高
    assert by["甲词"]["score"] > by["乙词"]["score"]
    assert "蓝海机会" in by["甲词"]["suggest"]
    assert "竞争激烈" in by["乙词"]["suggest"]
