"""API 端到端测试（mock 为主，UUMit 集成做条件测试）。"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shopmonitor.api.main import app

c = TestClient(app)

_EXPECTED_PLATFORMS = {"jd", "pdd", "douyin", "taobao", "shopee", "amazon", "aliexpress", "mock"}


def test_panel_and_bigscreen_routes():
    panel = c.get("/")
    assert panel.status_code == 200
    assert "深色" in panel.text or "data-theme" in panel.text
    bs = c.get("/大屏")
    assert bs.status_code == 200
    assert "电商数据大屏" in bs.text
    assert c.get("/bigscreen").status_code == 200


def test_tools_filter_mock():
    r = c.get("/api/v1/工具/筛选?platform=mock&category=数码&price_max=200&min_sales=100")
    assert r.status_code == 200
    j = r.json()
    assert j["count"] >= 1
    for it in j["items"]:
        assert it["price"] is None or it["price"] <= 200
        assert it["sales"] is None or it["sales"] >= 100
    scores = [it["score"] for it in j["items"]]
    assert scores == sorted(scores, reverse=True)


def test_compare_json():
    r = c.get("/api/v1/报告/对比?fmt=json&platform=mock&product_ids=demo-001,demo-002")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert all("title" in x and "price" in x for x in rows)


def test_watch_overview_endpoint():
    r = c.get("/api/v1/监控/关注总览")
    assert r.status_code == 200
    j = r.json()
    assert "count" in j and "items" in j


def test_batch_import_endpoint():
    r = c.post("/api/v1/监控/批量导入", json={"text": "https://item.jd.com/100012345.html\njd:8888888"})
    assert r.status_code == 200
    j = r.json()
    assert j["added"] == 2
    assert j["total"] == 2


def test_hot_trend_endpoint():
    r = c.get("/api/v1/uumit/热搜趋势?platform=douyin&days=7")
    assert r.status_code == 200
    j = r.json()
    assert j["platform"] == "douyin"
    assert "items" in j


def test_settings_status():
    r = c.get("/api/v1/配置/状态")
    assert r.status_code == 200
    j = r.json()
    assert j["count"] >= 16
    assert any(x["key"] == "ai" for x in j["items"])
    assert any(x["key"] == "jd_union" for x in j["items"])
    assert any(x["key"] == "douyin_mall" for x in j["items"])
    assert any(x["key"] == "taobao_open" for x in j["items"])


def test_source_template_download():
    r = c.get("/api/v1/配置/数据源模板")
    assert r.status_code == 200
    assert '"items"' in r.text


def test_plan_status():
    r = c.get("/api/v1/套餐/状态")
    assert r.status_code == 200
    j = r.json()
    assert j["plan"] in ("free", "pro", "enterprise")
    assert "max_watches" in j["limits"]


def test_plan_limit_enforced(monkeypatch):
    import shopmonitor.config as cfg
    monkeypatch.setattr(cfg, "PLAN_LIMITS", {"max_watches": 0, "ai": False, "en_report": True})
    r = c.post("/api/v1/monitor/watches", json={"platform": "mock", "mode": "keyword", "keyword": "测试"})
    assert r.status_code == 403
    assert "套餐" in r.json()["detail"]


def test_compare_report_en():
    r = c.get("/api/v1/报告/对比?fmt=md&lang=en&platform=mock&product_ids=demo-001")
    assert r.status_code == 200
    assert "Platform" in r.text and "Title" in r.text


def test_new_arrivals_endpoint():
    r = c.get("/api/v1/监控/新品榜?days=7")
    assert r.status_code == 200
    j = r.json()
    assert "count" in j and "items" in j


def test_custom_docs_page():
    r = c.get("/接口文档")
    assert r.status_code == 200
    assert "快速开始" in r.text
    assert "电商配置引导" in r.text
    assert "接口目录" in r.text
    assert c.get("/api-docs").status_code == 200


def test_settings_editable():
    r = c.get("/api/v1/配置/可配置项")
    assert r.status_code == 200
    j = r.json()
    keys = {x["key"] for x in j["items"]}
    assert "AI_LLM_API_KEY" in keys
    assert "SHOPMONITOR_WEBHOOK_URL" in keys
    assert "SHOPMONITOR_PLAN" in keys
    # 官方开放平台凭证
    for k in ("DOUYIN_MALL_APP_ID", "DOUYIN_MALL_SECRET", "TAOBAO_APP_KEY",
              "TAOBAO_APP_SECRET", "PDD_CLIENT_ID", "PDD_CLIENT_SECRET",
              "ALIBABA_APP_KEY", "KUAISHOU_APP_KEY"):
        assert k in keys, k


def test_settings_save_writes_env(monkeypatch, tmp_path):
    import shopmonitor.config as cfg
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path)
    (tmp_path / "配置文件.env").write_text("AI_LLM_API_KEY=old\n", encoding="utf-8")
    r = c.post("/api/v1/配置/保存?restart=false",
               json={"items": [{"key": "AI_LLM_API_KEY", "value": "sk-new"}]})
    assert r.status_code == 200
    assert r.json()["restarting"] is False
    text = (tmp_path / "配置文件.env").read_text(encoding="utf-8")
    assert "AI_LLM_API_KEY=sk-new" in text


def test_settings_save_rejects_unknown(monkeypatch, tmp_path):
    import shopmonitor.config as cfg
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path)
    r = c.post("/api/v1/配置/保存?restart=false",
               json={"items": [{"key": "SHOPMONITOR_PORT", "value": "9999"}]})
    assert r.status_code == 400


def test_settings_test_source_ok(tmp_path):
    f = tmp_path / "src.json"
    f.write_text('{"items": [{"product_id": "1", "title": "x", "price": 1.0}]}', encoding="utf-8")
    r = c.post("/api/v1/配置/测试数据源", json={"url": str(f)})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["count"] == 1


def test_settings_test_source_bad():
    r = c.post("/api/v1/配置/测试数据源", json={"url": "not-a-real-url-xxx"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_health_and_platforms():
    assert c.get("/health").json()["status"] == "ok"
    j = c.get("/api/v1/platforms").json()
    plats = {p["platform"] for p in j["platforms"]}
    assert _EXPECTED_PLATFORMS <= plats


def test_rank_mock():
    r = c.get("/api/v1/rank/mock?category=数码&limit=5")
    assert r.status_code == 200
    j = r.json()
    assert j["source"] in ("live", "cache")
    assert len(j["items"]) == 5
    it = j["items"][0]
    assert it["product_id"].startswith("demo-")
    # 新监控字段
    assert it["rating"] is not None
    assert it["review_count"] is not None
    assert it["stock_status"] in ("现货", "预售", "缺货")


def test_rank_taobao_fallback_mock():
    r = c.get("/api/v1/rank/taobao?limit=3")
    assert r.status_code == 200
    j = r.json()
    assert j["degraded"] is True
    assert j["source"] == "mock"
    assert len(j["items"]) == 3


def test_search_mock():
    r = c.get("/api/v1/search/mock?keyword=美妆&limit=3")
    assert r.status_code == 200
    j = r.json()
    assert j["keyword"] == "美妆"
    assert len(j["items"]) == 3


def test_history_and_change():
    # 抓两次（fresh=true 强制刷新），产生 2 条历史
    c.get("/api/v1/rank/mock?category=数码&limit=3&fresh=true")
    j = c.get("/api/v1/rank/mock?category=数码&limit=3&fresh=true").json()
    pid = j["items"][0]["product_id"]
    h = c.get(f"/api/v1/product/mock/{pid}/history?limit=5")
    assert h.status_code == 200
    assert len(h.json()["records"]) >= 2
    ch = c.get(f"/api/v1/product/mock/{pid}/change")
    assert ch.status_code == 200
    cj = ch.json()
    assert cj["product_id"] == pid
    assert cj["direction"] in ("up", "down", "flat")
    p = c.get(f"/api/v1/product/mock/{pid}")
    assert p.status_code == 200
    assert p.json()["product_id"] == pid


def test_chinese_path_aliases():
    """中文路径别名可用且与英文路径等价。"""
    r = c.get("/api/v1/榜单/mock?category=数码&limit=2")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    s = c.get("/api/v1/搜索/mock?keyword=美妆&limit=2")
    assert s.status_code == 200 and s.json()["keyword"] == "美妆"
    plats = c.get("/api/v1/平台列表")
    assert plats.status_code == 200 and len(plats.json()["platforms"]) >= 8
    j = c.get("/api/v1/rank/mock?category=数码&limit=2&fresh=true").json()
    pid = j["items"][0]["product_id"]
    assert c.get(f"/api/v1/商品/mock/{pid}/历史").status_code == 200
    assert c.get(f"/api/v1/商品/mock/{pid}/涨跌").status_code == 200

def test_compare_report_formats():
    j = c.get("/api/v1/rank/mock?category=数码&limit=2").json()
    ids = ",".join(i["product_id"] for i in j["items"])
    md = c.get(f"/api/v1/report/compare?platform=mock&product_ids={ids}&fmt=md")
    assert md.status_code == 200 and "促销" in md.text and "评分" in md.text
    csv_ = c.get(f"/api/v1/report/compare?platform=mock&product_ids={ids}&fmt=csv")
    assert csv_.status_code == 200 and "促销" in csv_.text
    xlsx = c.get(f"/api/v1/report/compare?platform=mock&product_ids={ids}&fmt=xlsx")
    assert xlsx.status_code == 200 and xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats"
    )


@pytest.mark.skipif(
    not (Path.home() / ".codex" / "skills" / "uumit-agent" / "scripts" / "rest_request.js").exists(),
    reason="本机未安装 uumit-agent 技能",
)
def test_uumit_status_and_free_data():
    s = c.get("/api/v1/uumit/status")
    assert s.status_code == 200
    assert s.json()["account"]["connected"] is True
    fd = c.get("/api/v1/uumit/free-data?top=5")
    assert fd.status_code == 200
    caps = fd.json()["capabilities"]
    assert len(caps) >= 1
    api_id = caps[0]["api_id"]
    assert api_id
    call = c.post(f"/api/v1/uumit/data/{api_id}/call", json={"grain": "month"})
    assert call.status_code == 200
    j = call.json()
    assert j["status"] == "ok"
    assert j["charged_ut"] in ("0", 0)

def test_panel_chinese():
    """主路径返回中文看板。"""
    r = c.get("/")
    assert r.status_code == 200
    assert "选品监控面板" in r.text
    assert "平台" in r.text and "监控" in r.text and "告警" in r.text
    r2 = c.get("/面板")
    assert r2.status_code == 200
    assert "选品监控面板" in r2.text


def test_mock_title_no_marketing():
    j = c.get("/api/v1/rank/mock?category=数码&limit=2").json()
    for it in j["items"]:
        assert "精选" not in it["title"]
