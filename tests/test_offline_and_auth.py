# -*- coding: utf-8 -*-
"""离线样例兜底 / 面板访问口令 / 排名预估月销 测试。"""
import pytest


def test_estimate_monthly_sales():
    from shopmonitor.insights import estimate_monthly_sales
    assert estimate_monthly_sales("mock", rank=1, sales=500) == 500       # 有销量用销量
    assert estimate_monthly_sales("mock", rank=1) == 5000                 # 无销量按排名估算
    assert estimate_monthly_sales("amazon", rank=10) == int(20000 / (10 ** 0.8))
    assert estimate_monthly_sales("mock", rank=None, sales=None) is None


def test_uumit_offline_sample(monkeypatch):
    import shopmonitor.uumit_data as ud

    def boom(*a, **k):
        raise RuntimeError("UUMit 不可用")

    monkeypatch.setattr(ud.uumit_feed, "call_free_data_api", boom)
    ov = ud.market_overview()
    assert ov["source"] == "内置样例" and ov["order_count"] > 0
    pf = ud.platform_performance()
    assert pf["source"] == "内置样例" and len(pf["items"]) == 2
    hot = ud.douyin_hot()
    assert hot["source"] == "内置样例" and len(hot["items"]) >= 3
    sg = ud.taobao_suggest("手机")
    assert sg["source"] == "内置样例" and len(sg["items"]) >= 4
    # 大盘接口也能兜底
    dash = ud.dashboard(fresh=True)
    assert len(dash["cards"]) >= 5


def test_password_auth(monkeypatch):
    import shopmonitor.api.main as m
    monkeypatch.setattr(m, "SHOPMONITOR_PASSWORD", "test123")
    from fastapi.testclient import TestClient
    c = TestClient(m.app)
    r = c.get("/")
    assert r.status_code == 200 and "访问口令" in r.text          # 未登录 -> 登录页
    assert c.post("/login", json={"password": "wrong"}).status_code == 401
    good = c.post("/login", json={"password": "test123"})
    assert good.status_code == 200 and "shopmonitor_auth" in good.headers.get("set-cookie", "")
    r2 = c.get("/", cookies=good.cookies)
    assert "选品监控面板" in r2.text                              # 登录后可访问

def test_preset_data_and_enable(monkeypatch, tmp_path):
    import shopmonitor.preset_data as pd
    from shopmonitor.config import BASE_DIR
    n = pd.ensure_preset_files(BASE_DIR)
    assert n == 7
    d = pd.preset_dir(BASE_DIR)
    assert (d / "jd.json").exists() and (d / "amazon.json").exists()
    import json
    jd = json.loads((d / "jd.json").read_text(encoding="utf-8"))
    assert len(jd["items"]) >= 5 and jd["items"][0]["product_id"]
    # 接口（用 tmp_path 隔离 env 写入）
    import shopmonitor.config as cfg
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path)
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.post("/api/v1/配置/启用预置数据?restart=false")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["enabled"] == 7 and j["restarting"] is False


def test_ai_rule_fallback(monkeypatch):
    import shopmonitor.ai_analysis as ai
    monkeypatch.setattr(ai, "AI_LLM_API_KEY", "")
    monkeypatch.setattr(ai, "_collect_context", lambda keyword: {
        "keyword": keyword, "sections": {"联想词": "手机壳、手机膜、手机支架"}})
    r = ai.analyze_selection("手机配件")
    assert r["status"] == "rule"
    assert "手机壳" in r["analysis"]
    assert r["note"]


def test_fill_datapack_endpoint(monkeypatch, tmp_path):
    import shopmonitor.config as cfg
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path)
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    r = c.post("/api/v1/配置/填数据包?restart=false", json={"base_url": "https://u.github.io/repo"})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["enabled"] == 7 and j["restarting"] is False
    t = (tmp_path / "配置文件.env").read_text(encoding="utf-8")
    assert "https://u.github.io/repo/data/jd.json" in t
    r2 = c.post("/api/v1/配置/填数据包?restart=false", json={"base_url": ""})
    assert r2.status_code == 200 and r2.json()["ok"] is False
