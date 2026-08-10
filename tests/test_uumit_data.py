# -*- coding: utf-8 -*-
"""大盘数据（UUMit 免费）归一化逻辑测试：mock 网络，只验证解析与计算。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from shopmonitor import uumit_data


class FakeResp:
    def __init__(self, result, charged="0"):
        self._result = result
        self._charged = charged
    def get(self, k, d=None):
        return {"result": self._result, "charged_ut": self._charged}.get(k, d)


def _fake_platforms():
    return {
        "platform": "Taobao", "product_count": 55196, "avg_price": "362.83",
        "sales_count": "621092040", "avg_rating": None,
    }


def test_platform_performance_normalize(monkeypatch):
    raw_items = [
        _fake_platforms(),
        {"platform": "JD", "product_count": 12474, "avg_price": "2765.15",
         "sales_count": "2412529932", "avg_rating": "4.55"},
    ]
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": raw_items}}),
    )
    d = uumit_data.platform_performance(fresh=True)
    rows = {r["platform"]: r for r in d["items"]}
    assert "淘宝" in rows and "京东" in rows
    assert rows["淘宝"]["product_count"] == 55196
    assert rows["京东"]["avg_rating"] == 4.55
    assert d["charged_ut"] == "0"
    assert d["note"] == "UUMit 免费数据 · 真实 · 0 扣费"


def test_market_overview_normalize(monkeypatch):
    raw = {
        "code": 0, "data": {
            "product": {"id": "12", "name": "2024 Ecommerce Orders and Users Data", "description": "x"},
            "order_count": 382287, "user_count": 92404, "product_count": 1000,
            "category_count": 5, "brand_count": 15, "total_amount": "656083534.77",
            "avg_order_amount": "1716.21", "total_quantity": "477910",
            "avg_fulfillment_time": "45.99", "delivered_rate": "0.5993",
        },
    }
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp(raw),
    )
    d = uumit_data.market_overview(fresh=True)
    assert d["order_count"] == 382287
    assert d["user_count"] == 92404
    assert d["total_amount"] == 656083534.77
    assert d["avg_order_amount"] == 1716.21
    assert d["delivered_rate"] == 0.5993


def test_sales_trend_normalize_and_mom(monkeypatch):
    raw_items = [
        {"period": "2024-01", "order_count": 1693, "user_count": 1468,
         "total_amount": "2838383.66", "total_quantity": "2084", "avg_order_amount": "1676.54"},
        {"period": "2024-02", "order_count": 4951, "user_count": 4074,
         "total_amount": "8559275.75", "total_quantity": "6206", "avg_order_amount": "1728.80"},
    ]
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": raw_items}}),
    )
    d = uumit_data.sales_trend(grain="month", fresh=True)
    assert d["count"] == 2
    assert d["items"][0]["total_amount"] == 2838383.66
    assert d["mom_growth_pct"] is not None
    # (8559275.75 - 2838383.66) / 2838383.66 * 100 ≈ 201.57
    assert abs(d["mom_growth_pct"] - 201.57) < 0.1


def test_sales_trend_partial_last_month(monkeypatch):
    # 2025-01 为残月（仅 1530 单），环比应改用最后两个完整周期并标注
    raw_items = [
        {"period": "2024-11", "order_count": 67305, "total_amount": "114699691.28"},
        {"period": "2024-12", "order_count": 72464, "total_amount": "124711864.27"},
        {"period": "2025-01", "order_count": 1530, "total_amount": "2281145.95"},
    ]
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": raw_items}}),
    )
    d = uumit_data.sales_trend(grain="month", fresh=True)
    assert d["last_period_partial"] is True
    assert d["mom_growth_pct"] is not None
    # (124711864.27 - 114699691.28) / 114699691.28 * 100 ≈ 8.73
    assert abs(d["mom_growth_pct"] - 8.73) < 0.1


def _months():
    return [
        {"period": "2024-01", "order_count": 1693, "user_count": 1468,
         "total_amount": "2838383.66", "total_quantity": "2084", "avg_order_amount": "1676.54"},
        {"period": "2024-02", "order_count": 4951, "user_count": 4074,
         "total_amount": "8559275.75", "total_quantity": "6206", "avg_order_amount": "1728.80"},
        {"period": "2024-03", "order_count": 8992, "user_count": 7242,
         "total_amount": "15966035.16", "total_quantity": "11331", "avg_order_amount": "1775.58"},
        {"period": "2024-04", "order_count": 12832, "user_count": 10223,
         "total_amount": "22638824.78", "total_quantity": "16060", "avg_order_amount": "1764.25"},
    ]


def test_sales_trend_quarter_aggregation(monkeypatch):
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": _months()}}),
    )
    d = uumit_data.sales_trend(grain="quarter", date_from="2024-01-01", date_to="2024-12-31", fresh=True)
    assert [it["period"] for it in d["items"]] == ["2024-Q1", "2024-Q2"]
    q1 = d["items"][0]
    assert q1["total_amount"] == round(2838383.66 + 8559275.75 + 15966035.16, 2)
    assert q1["order_count"] == 1693 + 4951 + 8992
    assert q1["total_quantity"] == 2084 + 6206 + 11331
    assert abs(q1["avg_order_amount"] - q1["total_amount"] / q1["order_count"]) < 0.01


def test_sales_trend_year_aggregation(monkeypatch):
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": _months()}}),
    )
    d = uumit_data.sales_trend(grain="year", fresh=True)
    assert [it["period"] for it in d["items"]] == ["2024"]
    assert d["items"][0]["order_count"] == sum(m["order_count"] for m in _months())


def test_dashboard_report_md(monkeypatch):
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": _months()}}),
    )
    monkeypatch.setattr(
        uumit_data.uumit_feed, "account_status",
        lambda: {"connected": True, "ut_balance": 810.0},
    )
    md = uumit_data.dashboard_report(fmt="md", fresh=True)
    assert "电商大盘数据报告" in md
    assert "一、大盘概览" in md
    assert "二、跨平台商品表现" in md
    assert "三、销售趋势" in md
    assert "2024-01" in md


def test_dashboard_report_csv(monkeypatch):
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": _months()}}),
    )
    csv_text = uumit_data.dashboard_report(fmt="csv", fresh=True)
    assert csv_text.startswith("\ufeff板块,指标,数值")  # UTF-8 BOM 开头，Excel 不乱码
    assert "平台对比" in csv_text
    assert "销售趋势" in csv_text


def test_sales_trend_date_filter_drops_outlier(monkeypatch):
    # 上游 dateTo=2024-12-31 仍带回 2025-01 残月，本地应精确剔除
    raw = _months() + [{"period": "2025-01", "order_count": 1530,
                        "user_count": 1400, "total_amount": "2281145.95",
                        "total_quantity": "1899", "avg_order_amount": "1490.95"}]
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": raw}}),
    )
    d = uumit_data.sales_trend(grain="month", date_from="2024-01-01", date_to="2024-12-31", fresh=True)
    assert [it["period"] for it in d["items"]] == ["2024-01", "2024-02", "2024-03", "2024-04"]
    assert d["last_period_partial"] is False


def test_overview_cards(monkeypatch):
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {
            "product": {"id": "12", "name": "x", "description": "y"},
            "order_count": 382287, "user_count": 92404, "product_count": 1000,
            "category_count": 5, "brand_count": 15, "total_amount": "656083534.77",
            "avg_order_amount": "1716.21", "total_quantity": "477910",
            "avg_fulfillment_time": "45.99", "delivered_rate": "0.5993",
        }}),
    )
    cards = uumit_data.overview_cards(fresh=True)
    labels = [c["label"] for c in cards]
    assert "订单数" in labels and "成交额" in labels and "发货率" in labels and "平均履约(小时)" in labels
    assert len(cards) == 10


def test_taobao_suggest_parse(monkeypatch):
    raw = '{"code":1,"msg":"查询成功","data":[{"sp":"手机壳","xsd":"100"},{"sp":"手机膜","xsd":"99"}],"tips":"ok"}'
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: {"status": "ok", "charged_ut": "0", "result": raw},
    )
    d = uumit_data.taobao_suggest("手机", fresh=True)
    assert d["keyword"] == "手机"
    assert d["count"] == 2
    assert d["items"][0]["word"] == "手机壳"
    assert d["items"][0]["score"] == "100"


def test_douyin_hot_parse(monkeypatch):
    raw = {"code": "100", "data": [
        {"hot": 11416656, "url": "https://www.douyin.com/video/1", "title": "今日立秋"},
        {"hot": 11381248, "url": "https://www.douyin.com/video/2", "title": "台风实时路径"},
    ]}
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: {"status": "ok", "charged_ut": "0", "result": raw},
    )
    d = uumit_data.douyin_hot(fresh=True)
    assert d["count"] == 2
    assert d["items"][0]["rank"] == 1
    assert d["items"][0]["title"] == "今日立秋"
    assert d["items"][0]["hot"] == 11416656
    assert "douyin.com" in d["items"][1]["url"]


def test_json_loads_lenient_trailing_comma():
    raw = '{"code":1,"data":[{"sp":"a","xsd":"1"},{"sp":"b","xsd":"2"},],"tips":"x"}'
    obj = uumit_data._json_loads_lenient(raw)
    assert len(obj["data"]) == 2


def test_taobao_suggest_trailing_comma(monkeypatch):
    # 上游真实返回带尾逗号 ,]，必须能解析
    raw = '{"code":1,"msg":"查询成功","data":[{"sp":"手机壳","xsd":"100"},],"tips":"淘宝联想词"}'
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: {"status": "ok", "charged_ut": "0", "result": raw},
    )
    d = uumit_data.taobao_suggest("手机", fresh=True)
    assert d["count"] == 1
    assert d["items"][0]["word"] == "手机壳"


def test_taobao_suggest_requires_keyword(monkeypatch):
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: {"status": "ok", "charged_ut": "0", "result": "{}"},
    )
    try:
        uumit_data.taobao_suggest("  ", fresh=True)
        assert False, "应抛 UumitError"
    except uumit_data.uumit_feed.UumitError:
        pass


def test_baidu_hot_parse(monkeypatch):
    raw = {"code": 0, "msg": "获取成功", "data": [
        {"link": "https://www.baidu.com/s?wd=x", "index": "7903980", "title": "各美其美 美美与共"},
        {"link": "https://www.baidu.com/s?wd=y", "index": "7800000", "title": "今日热搜"},
    ]}
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: {"status": "ok", "charged_ut": "0", "result": raw},
    )
    d = uumit_data.baidu_hot(type_="realtime", fresh=True)
    assert d["type_name"] == "实时"
    assert d["count"] == 2
    assert d["items"][0]["rank"] == 1
    assert d["items"][0]["title"] == "各美其美 美美与共"
    assert d["items"][0]["index"] == "7903980"
    assert "baidu.com" in d["items"][0]["url"]


def test_hot_words_report_md(monkeypatch):
    def fake_call(api_id, body):
        if api_id == uumit_data.API_DOUYIN_HOT:
            return {"status": "ok", "charged_ut": "0", "result": {"data": [{"hot": 11416656, "title": "今日立秋", "url": "u"}]}}
        if api_id == uumit_data.API_BAIDU_HOT:
            return {"status": "ok", "charged_ut": "0", "result": {"data": [{"index": "7903980", "title": "百度热", "link": "l"}]}}
        return {"status": "ok", "charged_ut": "0", "result": '{"code":1,"data":[{"sp":"手机壳","xsd":"100"}],"tips":"t"}'}
    monkeypatch.setattr(uumit_data.uumit_feed, "call_free_data_api", fake_call)
    md = uumit_data.hot_words_report(fmt="md", keyword="手机", fresh=True)
    assert "热搜选词报告" in md
    assert "抖音实时热搜" in md
    assert "百度热搜" in md
    assert "淘宝联想词" in md
    assert "今日立秋" in md and "百度热" in md and "手机壳" in md


def test_hot_words_report_csv(monkeypatch):
    def fake_call(api_id, body):
        if api_id == uumit_data.API_DOUYIN_HOT:
            return {"status": "ok", "charged_ut": "0", "result": {"data": [{"hot": 1, "title": "t", "url": "u"}]}}
        if api_id == uumit_data.API_BAIDU_HOT:
            return {"status": "ok", "charged_ut": "0", "result": {"data": [{"index": "1", "title": "b", "link": "l"}]}}
        return {"status": "ok", "charged_ut": "0", "result": '{"code":1,"data":[{"sp":"w","xsd":"1"}]}'}
    monkeypatch.setattr(uumit_data.uumit_feed, "call_free_data_api", fake_call)
    csv_text = uumit_data.hot_words_report(fmt="csv", keyword="手机", fresh=True)
    assert csv_text.startswith("\ufeff板块,排名,标题")
    assert "抖音热搜" in csv_text and "百度热搜" in csv_text and "淘宝联想词" in csv_text


def test_dashboard_aggregates(monkeypatch):
    monkeypatch.setattr(
        uumit_data.uumit_feed, "call_free_data_api",
        lambda api_id, body: FakeResp({"code": 0, "data": {"items": [_fake_platforms()]}}),
    )
    monkeypatch.setattr(
        uumit_data.uumit_feed, "account_status",
        lambda: {"connected": True, "ut_balance": 810.0, "ut_available": 810.0},
    )
    d = uumit_data.dashboard(fresh=True)
    assert d["account"]["ut_balance"] == 810.0
    assert len(d["platforms"]["items"]) == 1
    assert len(d["free_apis"]) == 3
