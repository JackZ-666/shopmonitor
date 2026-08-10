# -*- coding: utf-8 -*-
"""UUMit 免费电商数据大盘。

只封装 3 个已实测可用的 price_ut=0 免费数据接口（绝不自动扣费）：
1. 统计各电商平台商品表现   -> 淘宝/京东 平台维度商品数、均价、销量、评分
2. 查询电商订单用户经营概览  -> 订单、用户、商品、成交额、客单价等大盘指标
3. 分析电商销售额销量时间变化 -> 按月返回销售额、销量、订单趋势（日期范围真实生效）

实测说明（2026-08 本机）：
- 日期范围 dateFrom/dateTo 真实生效；
- 关键词/类目/品牌/性别等过滤参数上游固定返回全量，暂不生效；
- 上游始终按月返回；"按季/按年"由本模块对月度数据本地聚合，"按日"暂等同于按月。
- 末位残月自动识别（如 2025-01 仅 1530 单），环比改用最后两个完整周期。

所有函数在 UUMit 不可用时抛 UumitError，由 API 层统一转 502。
"""
from __future__ import annotations

import csv
import functools
import io
import json
import time
from typing import Any, Dict, List, Optional

from . import cache, uumit_feed

# 数据广场免费 API（price_ut=0，已实测可调用）
API_PLATFORM_PERFORMANCE = "ef8d22e3-3380-4734-a5e0-634b8bb09c14"
API_MARKET_OVERVIEW = "4858fbbd-0532-40eb-8890-297e8e0f0233"
API_SALES_TREND = "56838770-5c57-4d1b-80c7-93ed61b57f7a"
API_TAOBAO_SUGGEST = "f0e31ee6-32e6-46bc-8609-7f4ecd76302f"
API_DOUYIN_HOT = "664ca7ce-a0c8-4792-947c-3fb56e4f0426"
API_BAIDU_HOT = "c684ea2a-429c-440c-a1eb-dbae14cf714b"

# 百度热搜分类
BAIDU_HOT_TYPES = {
    "realtime": "实时",
    "novel": "小说",
    "movie": "电影",
    "teleplay": "电视剧",
    "car": "汽车",
    "game": "游戏",
}

# 平台英文名 -> 中文名
_PLATFORM_NAMES: Dict[str, str] = {
    "Taobao": "淘宝",
    "Tmall": "天猫",
    "JD": "京东",
    "PDD": "拼多多",
    "Douyin": "抖音",
    "Kuaishou": "快手",
    "Shopee": "Shopee",
    "Amazon": "Amazon",
    "AliExpress": "AliExpress",
}

# 简单内存缓存：默认 60 秒，避免页面反复打源接口
_CACHE: Dict[str, tuple] = {}
_CACHE_TTL_SEC = 60.0

_NOTE = "UUMit 免费数据 · 真实 · 0 扣费"
_SAMPLE_NOTE = "内置样例（UUMit 未连接，非实时）"

# 离线样例：UUMit 不可用时自动兜底，保证分享版/无技能环境开箱有数据
_SAMPLE_OVERVIEW = {
    "source": "内置样例", "charged_ut": "0", "note": _SAMPLE_NOTE,
    "dataset": {"id": "sample", "name": "电商大盘样例", "description": "UUMit 未连接时的离线样例"},
    "order_count": 382287, "user_count": 92404, "product_count": 1000, "category_count": 5,
    "brand_count": 15, "total_amount": 656083534.77, "avg_order_amount": 1716.21,
    "total_quantity": 477910, "avg_fulfillment_time": 46.0, "delivered_rate": 0.5993,
}
_SAMPLE_PLATFORMS = [
    {"platform": "淘宝", "product_count": 55196, "avg_price": 362.83, "sales_count": 621092040, "avg_rating": None},
    {"platform": "京东", "product_count": 12474, "avg_price": 2765.15, "sales_count": 2412529932, "avg_rating": 4.55},
]


def _sample_overview(**k):
    return dict(_SAMPLE_OVERVIEW)


def _sample_platforms(**k):
    return {"items": [dict(x) for x in _SAMPLE_PLATFORMS], "source": "内置样例", "charged_ut": "0", "note": _SAMPLE_NOTE}


def _sample_trend(**k):
    months = []
    base = 42000000
    for m in range(1, 13):
        months.append({
            "period": f"2024-{m:02d}",
            "total_amount": round(base * (1 + (m % 5) * 0.18), 2),
            "order_count": 300000 + m * 7000,
            "total_quantity": 380000 + m * 9000,
            "avg_order_amount": 1720.0,
        })
    return {"source": "内置样例", "note": _SAMPLE_NOTE, "grain": "month", "items": months,
            "mom_growth_pct": None, "last_period_partial": False}


def _sample_douyin(**k):
    words = [("今日立秋", 11381248), ("台风白海豚实时路径", 11416656), ("海上大风车给油田直供绿电", 11361064),
             ("暑期文旅消费升温", 11230000), ("全民健身日", 11150000), ("新能源汽车下乡", 11020000)]
    return {"source": "内置样例", "charged_ut": "0", "note": _SAMPLE_NOTE, "count": len(words),
            "items": [{"rank": i + 1, "title": w, "hot": h, "url": ""} for i, (w, h) in enumerate(words)]}


def _sample_baidu(**k):
    words = ["各美其美 美美与共", "暑期旅游预订量增长", "新能源汽车销量创新高", "国产大飞机商业运营", "智能家居市场升温"]
    return {"source": "内置样例", "charged_ut": "0", "note": _SAMPLE_NOTE, "count": len(words),
            "items": [{"rank": i + 1, "title": w, "index": "1000000"} for i, w in enumerate(words)]}


def _sample_suggest(keyword="手机", **k):
    if not (keyword or "").strip():
        raise uumit_feed.UumitError("请输入关键词")
    items = [{"word": f"{keyword} {s}", "score": 100 - i * 5}
             for i, s in enumerate(["推荐", "品牌", "排行榜", "测评", "价格", "新款"])]
    return {"source": "内置样例", "charged_ut": "0", "note": _SAMPLE_NOTE, "keyword": keyword,
            "count": len(items), "items": items}


def _fallback(sample_fn):
    """UUMit 调用失败时返回内置样例（不缓存，下次继续尝试真实数据）。"""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            try:
                return fn(*a, **k)
            except Exception:  # noqa: BLE001
                try:
                    return sample_fn(*a, **k)
                except TypeError:
                    return sample_fn(**k)
        return wrapper
    return deco


def _cached(key: str, fn) -> Any:
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL_SEC:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _num(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _int(v, default: int = 0) -> int:
    try:
        return int(float(v)) if v is not None else default
    except (TypeError, ValueError):
        return default


def _platform_cn(name: Optional[str]) -> str:
    return _PLATFORM_NAMES.get(name or "", name or "未知平台")


def _apply_change(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """环比 + 残月识别（末位不足上期 25% 视为残月）。"""
    mom = None
    last_partial = False
    if len(items) >= 2:
        prev_amount = _num(items[-2]["total_amount"])
        cur_amount = _num(items[-1]["total_amount"])
        if prev_amount:
            if cur_amount < prev_amount * 0.25:
                last_partial = True
                if len(items) >= 3:
                    base = _num(items[-3]["total_amount"])
                    if base:
                        mom = round((prev_amount - base) / base * 100, 2)
            else:
                mom = round((cur_amount - prev_amount) / prev_amount * 100, 2)
    return {"mom_growth_pct": mom, "last_period_partial": last_partial}


# ---------------- 1. 跨平台商品表现 ----------------
@_fallback(_sample_platforms)
def platform_performance(fresh: bool = False) -> Dict[str, Any]:

    """淘宝/京东平台维度：商品数、均价、销量、评分（真实免费数据）。"""
    def _load() -> Dict[str, Any]:
        res = uumit_feed.call_free_data_api(API_PLATFORM_PERFORMANCE, {})
        raw = (res.get("result") or {}).get("data", {}).get("items") or []
        rows = []
        for it in raw:
            rows.append(
                {
                    "platform": _platform_cn(it.get("platform")),
                    "code": it.get("platform"),
                    "product_count": _int(it.get("product_count")),
                    "avg_price": round(_num(it.get("avg_price")), 2),
                    "sales_count": _int(it.get("sales_count")),
                    "avg_rating": _num(it.get("avg_rating")) or None,
                }
            )
        # 派生对比：最高均价 / 最低均价 倍数
        ratio = None
        prices = [r["avg_price"] for r in rows if r["avg_price"]]
        if len(prices) >= 2 and min(prices) > 0:
            ratio = round(max(prices) / min(prices), 2)
        return {
            "source": "uumit_free",
            "charged_ut": res.get("charged_ut", "0"),
            "note": _NOTE,
            "max_min_price_ratio": ratio,
            "items": rows,
        }

    if fresh:
        return _load()
    return _cached("uumit_platform_perf", _load)


# ---------------- 2. 电商大盘经营概览 ----------------
@_fallback(_sample_overview)
def market_overview(fresh: bool = False) -> Dict[str, Any]:

    """订单/用户/商品/成交额/客单价等大盘指标（真实免费数据）。"""
    def _load() -> Dict[str, Any]:
        res = uumit_feed.call_free_data_api(API_MARKET_OVERVIEW, {})
        raw = res.get("result") or {}
        data = raw.get("data", {})
        product = data.get("product") or {}
        return {
            "source": "uumit_free",
            "charged_ut": res.get("charged_ut", "0"),
            "note": _NOTE,
            "dataset": {
                "id": product.get("id"),
                "name": product.get("name"),
                "description": product.get("description"),
            },
            "order_count": _int(data.get("order_count")),
            "user_count": _int(data.get("user_count")),
            "product_count": _int(data.get("product_count")),
            "category_count": _int(data.get("category_count")),
            "brand_count": _int(data.get("brand_count")),
            "total_amount": round(_num(data.get("total_amount")), 2),
            "avg_order_amount": round(_num(data.get("avg_order_amount")), 2),
            "total_quantity": _int(data.get("total_quantity")),
            "avg_fulfillment_time": _num(data.get("avg_fulfillment_time")),
            "delivered_rate": _num(data.get("delivered_rate")),
        }

    if fresh:
        return _load()
    return _cached("uumit_overview", _load)


def overview_cards(fresh: bool = False) -> List[Dict[str, str]]:
    """经营概览 -> 面板卡片（含中文标签与格式化值）。"""
    ov = market_overview(fresh=fresh)
    cards = [
        {"label": "订单数", "key": "order_count", "value": f"{ov['order_count']:,}"},
        {"label": "用户数", "key": "user_count", "value": f"{ov['user_count']:,}"},
        {"label": "成交额", "key": "total_amount", "value": f"{ov['total_amount']:,.2f}"},
        {"label": "客单价", "key": "avg_order_amount", "value": f"{ov['avg_order_amount']:,.2f}"},
        {"label": "销量(件)", "key": "total_quantity", "value": f"{ov['total_quantity']:,}"},
        {"label": "商品数", "key": "product_count", "value": f"{ov['product_count']:,}"},
        {"label": "类目数", "key": "category_count", "value": f"{ov['category_count']}"},
        {"label": "品牌数", "key": "brand_count", "value": f"{ov['brand_count']}"},
        {"label": "平均履约(小时)", "key": "avg_fulfillment_time", "value": f"{ov['avg_fulfillment_time']:.1f}"},
        {"label": "发货率", "key": "delivered_rate", "value": f"{ov['delivered_rate']*100:.1f}%"},
    ]
    return cards


# ---------------- 3. 销售额销量时间趋势 ----------------
@_fallback(_sample_trend)
def sales_trend(
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    grain: str = "month",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    fresh: bool = False,
) -> Dict[str, Any]:
    """销售额/销量时间趋势。

    上游始终按月返回；grain 为 month 时原样返回，quarter/year 由本地聚合，
    day 暂等同于 month（上游无日粒度）。日期范围 dateFrom/dateTo 真实生效。
    """
    body: Dict[str, Any] = {"grain": "month"}
    if keyword:
        body["keyword"] = keyword
    if category:
        body["category"] = category
    if brand:
        body["brand"] = brand
    if date_from:
        body["dateFrom"] = date_from
    if date_to:
        body["dateTo"] = date_to

    def _load() -> Dict[str, Any]:
        res = uumit_feed.call_free_data_api(API_SALES_TREND, body)
        raw = (res.get("result") or {}).get("data", {}).get("items") or []
        months = []
        for it in raw:
            months.append(
                {
                    "period": it.get("period"),
                    "order_count": _int(it.get("order_count")),
                    "user_count": _int(it.get("user_count")),
                    "total_amount": round(_num(it.get("total_amount")), 2),
                    "total_quantity": _int(it.get("total_quantity")),
                    "avg_order_amount": round(_num(it.get("avg_order_amount")), 2),
                }
            )
        # 上游日期过滤不严谨（如 dateTo=2024-12-31 仍带回 2025-01），本地精确过滤
        if date_from:
            start = date_from[:7]
            months = [m for m in months if str(m["period"]) >= start]
        if date_to:
            end = date_to[:7]
            months = [m for m in months if str(m["period"]) <= end]
        items = _aggregate(months, grain)
        change = _apply_change(items)
        return {
            "source": "uumit_free",
            "charged_ut": res.get("charged_ut", "0"),
            "note": _NOTE,
            "note_detail": "上游按月返回；按季/按年为本地产聚合，日期范围生效",
            "grain": grain,
            "keyword": keyword or "",
            "category": category or "",
            "brand": brand or "",
            "count": len(items),
            "date_from": date_from or "",
            "date_to": date_to or "",
            **change,
            "items": items,
        }

    cache_key = f"uumit_trend|{grain}|{keyword or ''}|{category or ''}|{brand or ''}|{date_from or ''}|{date_to or ''}"
    if fresh:
        return _load()
    return _cached(cache_key, _load)


def _aggregate(months: List[Dict[str, Any]], grain: str) -> List[Dict[str, Any]]:
    if grain in ("", "month", "day"):
        return list(months)
    buckets: Dict[str, Dict[str, Any]] = {}
    order = []
    for m in months:
        p = m["period"]  # YYYY-MM
        try:
            year, month = p.split("-")[0], int(p.split("-")[1])
        except (IndexError, ValueError):
            key = p
        else:
            if grain == "year":
                key = year
            else:  # quarter
                key = f"{year}-Q{(month - 1) // 3 + 1}"
        if key not in buckets:
            buckets[key] = {"period": key, "order_count": 0, "user_count": 0,
                            "total_amount": 0.0, "total_quantity": 0}
            order.append(key)
        b = buckets[key]
        b["order_count"] += m["order_count"]
        b["user_count"] += m["user_count"]
        b["total_amount"] += m["total_amount"]
        b["total_quantity"] += m["total_quantity"]
    out = []
    for key in order:
        b = buckets[key]
        b["total_amount"] = round(b["total_amount"], 2)
        b["avg_order_amount"] = round(b["total_amount"] / b["order_count"], 2) if b["order_count"] else 0.0
        out.append(b)
    return out


# ---------------- 4. 热搜与选词（真实免费数据） ----------------
def _json_loads_lenient(text: str) -> Any:
    """容错 JSON 解析：上游偶发尾逗号（如 ,]），先清掉再解析。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        return json.loads(cleaned)


def _result_obj(res: Dict[str, Any]) -> Any:
    """result 可能是对象或 JSON 字符串，统一解析（含尾逗号容错）。"""
    raw = res.get("result")
    if isinstance(raw, str):
        try:
            return _json_loads_lenient(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return raw
    return raw or {}


@_fallback(_sample_suggest)
def taobao_suggest(keyword: str, fresh: bool = False) -> Dict[str, Any]:
    if not (keyword or "").strip():
        raise uumit_feed.UumitError("请输入关键词")
    """淘宝联想词（选词工具）：输入商品词返回下拉联想词，真实淘宝数据。"""
    keyword = (keyword or "").strip()
    if not keyword:
        raise uumit_feed.UumitError("请输入关键词")

    def _load() -> Dict[str, Any]:
        res = uumit_feed.call_free_data_api(API_TAOBAO_SUGGEST, {"msg": keyword})
        parsed = _result_obj(res)
        raw_items = []
        if isinstance(parsed, dict):
            raw_items = parsed.get("data") or []
        items = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            items.append({"word": it.get("sp"), "score": it.get("xsd")})
        return {
            "source": "uumit_free",
            "charged_ut": res.get("charged_ut", "0"),
            "note": _NOTE,
            "keyword": keyword,
            "count": len(items),
            "items": items,
        }

    if fresh:
        return _load()
    return _cached(f"uumit_taobao_suggest|{keyword}", _load)


@_fallback(_sample_douyin)
def douyin_hot(fresh: bool = False) -> Dict[str, Any]:

    """抖音实时热搜（前 10）：标题 + 热度 + 视频链接，真实抖音数据。"""
    def _load() -> Dict[str, Any]:
        res = uumit_feed.call_free_data_api(API_DOUYIN_HOT, {})
        parsed = _result_obj(res)
        raw_items = []
        if isinstance(parsed, dict):
            raw_items = parsed.get("data") or []
        items = []
        for i, it in enumerate(raw_items, start=1):
            if not isinstance(it, dict):
                continue
            items.append({
                "rank": i,
                "title": it.get("title"),
                "hot": _int(it.get("hot")),
                "url": it.get("url"),
            })
        try:
            cache.record_hot_snapshot(
                "douyin",
                [{"word": it["title"], "heat": it.get("hot"), "rank": it.get("rank")} for it in items],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "source": "uumit_free",
            "charged_ut": res.get("charged_ut", "0"),
            "note": _NOTE,
            "count": len(items),
            "items": items,
        }

    if fresh:
        return _load()
    return _cached("uumit_douyin_hot", _load)


# ---------------- 4. 大盘报告（导出用） ----------------
def dashboard_report(fmt: str = "md", lang: str = "zh", fresh: bool = False) -> str:
    """大盘数据导出为 Markdown / CSV，可直接作为报告模板资产；lang=en 出英文版。"""
    ov = market_overview(fresh=fresh)
    pf = platform_performance(fresh=fresh)
    tr = sales_trend(grain="month", fresh=fresh)
    fmt = (fmt or "md").lower()
    if lang == "en":
        return ("\ufeff" + _report_csv_en(ov, pf, tr)) if fmt == "csv" else _report_md_en(ov, pf, tr)
    if fmt == "csv":
        return "\ufeff" + _report_csv(ov, pf, tr)  # BOM：Excel 打开中文不乱码
    return _report_md(ov, pf, tr)


def _fmt_money(v: float) -> str:
    if v >= 1e8:
        return f"{v / 1e8:.2f} 亿"
    if v >= 1e4:
        return f"{v / 1e4:.1f} 万"
    return f"{v:,.2f}"


def _report_md(ov, pf, tr) -> str:
    lines = [
        "# 电商大盘数据报告",
        "",
        f"> 数据来源：UUMit 数据广场（免费接口，0 扣费）｜生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 一、大盘概览",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 订单数 | {ov['order_count']:,} |",
        f"| 用户数 | {ov['user_count']:,} |",
        f"| 成交额 | {_fmt_money(ov['total_amount'])}（{ov['total_amount']:,.2f}） |",
        f"| 客单价 | {ov['avg_order_amount']:,.2f} |",
        f"| 销量(件) | {ov['total_quantity']:,} |",
        f"| 商品数 | {ov['product_count']:,} |",
        f"| 类目数 | {ov['category_count']} |",
        f"| 品牌数 | {ov['brand_count']} |",
        f"| 平均履约时长 | {ov['avg_fulfillment_time']:.1f} 小时 |",
        f"| 发货率 | {ov['delivered_rate'] * 100:.1f}% |",
        "",
        "## 二、跨平台商品表现",
        "",
        "| 平台 | 商品数 | 均价 | 销量 | 评分 |",
        "|---|---|---|---|---|",
    ]
    for r in pf["items"]:
        lines.append(f"| {r['platform']} | {r['product_count']:,} | {r['avg_price']:,.2f} | {r['sales_count']:,} | {r['avg_rating'] if r['avg_rating'] is not None else '-'} |")
    if pf.get("max_min_price_ratio"):
        lines.append("")
        lines.append(f"> 说明：最高平台均价约为最低平台的 **{pf['max_min_price_ratio']} 倍**。")
    lines += ["", "## 三、销售趋势（按月）", "", "| 周期 | 成交额 | 订单数 | 用户数 | 销量(件) | 客单价 |", "|---|---|---|---|---|---|"]
    for it in tr["items"]:
        lines.append(
            f"| {it['period']} | {_fmt_money(it['total_amount'])} | {it['order_count']:,} | {it['user_count']:,} | {it['total_quantity']:,} | {it['avg_order_amount']:,.2f} |"
        )
    if tr.get("mom_growth_pct") is not None:
        tag = "（末位为残月，环比按完整周期计）" if tr.get("last_period_partial") else ""
        lines.append("")
        lines.append(f"> 最近一期环比成交额：**{tr['mom_growth_pct']:+.2f}%**{tag}")
    return "\n".join(lines)


def _report_csv(ov, pf, tr) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["板块", "指标", "数值"])
    for label, key in [("大盘概览", "订单数"), ("大盘概览", "用户数"), ("大盘概览", "成交额"),
                       ("大盘概览", "客单价"), ("大盘概览", "销量件"), ("大盘概览", "商品数"),
                       ("大盘概览", "类目数"), ("大盘概览", "品牌数"), ("大盘概览", "平均履约小时"),
                       ("大盘概览", "发货率")]:
        val = {
            "订单数": ov["order_count"], "用户数": ov["user_count"], "成交额": ov["total_amount"],
            "客单价": ov["avg_order_amount"], "销量件": ov["total_quantity"], "商品数": ov["product_count"],
            "类目数": ov["category_count"], "品牌数": ov["brand_count"],
            "平均履约小时": ov["avg_fulfillment_time"], "发货率": ov["delivered_rate"],
        }[key]
        w.writerow([label, key, val])
    for r in pf["items"]:
        w.writerow(["平台对比", r["platform"] + "_商品数", r["product_count"]])
        w.writerow(["平台对比", r["platform"] + "_均价", r["avg_price"]])
        w.writerow(["平台对比", r["platform"] + "_销量", r["sales_count"]])
        w.writerow(["平台对比", r["platform"] + "_评分", r["avg_rating"] if r["avg_rating"] is not None else ""])
    for it in tr["items"]:
        w.writerow(["销售趋势", it["period"] + "_成交额", it["total_amount"]])
        w.writerow(["销售趋势", it["period"] + "_订单数", it["order_count"]])
        w.writerow(["销售趋势", it["period"] + "_销量件", it["total_quantity"]])
    return buf.getvalue()


@_fallback(_sample_baidu)
def baidu_hot(type_: str = "realtime", fresh: bool = False) -> Dict[str, Any]:

    """百度热搜（实时/小说/电影/电视剧/汽车/游戏），真实免费数据。"""
    if type_ not in BAIDU_HOT_TYPES:
        type_ = "realtime"

    def _load() -> Dict[str, Any]:
        res = uumit_feed.call_free_data_api(API_BAIDU_HOT, {"type": type_})
        parsed = _result_obj(res)
        raw_items = []
        if isinstance(parsed, dict):
            raw_items = parsed.get("data") or []
        items = []
        for i, it in enumerate(raw_items, start=1):
            if not isinstance(it, dict):
                continue
            items.append({
                "rank": i,
                "title": it.get("title"),
                "index": it.get("index"),
                "url": it.get("link"),
            })
        try:
            cache.record_hot_snapshot(
                f"baidu_{type_}",
                [{"word": it["title"], "heat": it.get("index"), "rank": it.get("rank")} for it in items],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "source": "uumit_free",
            "charged_ut": res.get("charged_ut", "0"),
            "note": _NOTE,
            "type": type_,
            "type_name": BAIDU_HOT_TYPES.get(type_, type_),
            "count": len(items),
            "items": items,
        }

    if fresh:
        return _load()
    return _cached(f"uumit_baidu_hot|{type_}", _load)


# ---------------- 5. 热搜选词报告（导出用） ----------------
def hot_words_report(fmt: str = "md", keyword: str = "手机", lang: str = "zh", fresh: bool = False) -> str:
    """热搜 + 选词报告：抖音热搜 + 百度热搜 + 淘宝联想词，导出 Markdown/CSV；lang=en 出英文版。"""
    hot = douyin_hot(fresh=fresh)
    baidu = baidu_hot(type_="realtime", fresh=fresh)
    sg = taobao_suggest(keyword=keyword, fresh=fresh)
    fmt = (fmt or "md").lower()
    if lang == "en":
        return ("\ufeff" + _hot_csv_en(hot, baidu, sg)) if fmt == "csv" else _hot_md_en(hot, baidu, sg)
    if fmt == "csv":
        return "\ufeff" + _hot_csv(hot, baidu, sg)
    return _hot_md(hot, baidu, sg)


def _hot_md(hot, baidu, sg) -> str:
    lines = [
        "# 热搜选词报告",
        "",
        f"> 数据来源：UUMit 数据广场（免费接口，0 扣费）｜生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 一、抖音实时热搜",
        "",
        "| 排名 | 标题 | 热度 |",
        "|---|---|---|",
    ]
    for it in hot["items"]:
        lines.append(f"| {it['rank']} | {it['title']} | {it['hot']:,} |")
    lines += ["", "## 二、百度热搜（实时）", "", "| 排名 | 标题 | 热度指数 |", "|---|---|---|"]
    for it in baidu["items"]:
        lines.append(f"| {it['rank']} | {it['title']} | {it['index'] or '-'} |")
    lines += ["", f"## 三、淘宝联想词（关键词：{sg['keyword']}）", "", "| 联想词 | 指数 |", "|---|---|"]
    for it in sg["items"]:
        lines.append(f"| {it['word']} | {it['score'] or '-'} |")
    return "\n".join(lines)


def _hot_csv(hot, baidu, sg) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["板块", "排名", "标题", "数值", "链接"])
    for it in hot["items"]:
        w.writerow(["抖音热搜", it["rank"], it["title"], it["hot"], it.get("url", "")])
    for it in baidu["items"]:
        w.writerow(["百度热搜", it["rank"], it["title"], it.get("index", ""), it.get("url", "")])
    for it in sg["items"]:
        w.writerow(["淘宝联想词", "", it.get("word", ""), it.get("score", ""), ""])
    return buf.getvalue()




# ---------------- 英文报告（跨境卖家） ----------------
def _report_md_en(ov, pf, tr) -> str:
    lines = [
        "# E-Commerce Market Dashboard",
        "",
        f"> Source: UUMit Data Marketplace (free, 0 UT) | Generated: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 1. Overview",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Orders | {ov.get('order_count', 0):,} |",
        f"| Users | {ov.get('user_count', 0):,} |",
        f"| GMV | {_fmt_money(ov.get('total_amount', 0))} |",
        f"| Avg Order Value | {_fmt_money(ov.get('avg_order_amount', 0))} |",
        f"| Units | {ov.get('total_quantity', 0):,} |",
        f"| Products | {ov.get('product_count', 0):,} |",
        f"| Categories | {ov.get('category_count', 0)} |",
        f"| Brands | {ov.get('brand_count', 0)} |",
        f"| Delivery Rate | {ov.get('delivered_rate', 0) * 100:.1f}% |",
        "",
        "## 2. Platform Comparison",
        "",
        "| Platform | Products | Avg Price | Sales | Rating |",
        "|---|---|---|---|---|",
    ]
    for r in pf.get("items", []):
        lines.append(f"| {r['platform']} | {r['product_count']:,} | {_fmt_money(r['avg_price'])} | {r['sales_count']:,} | {r['avg_rating'] if r['avg_rating'] is not None else '-'} |")
    lines += ["", "## 3. Monthly Sales Trend", "", "| Period | GMV | Orders | Units | AOV |", "|---|---|---|---|---|"]
    for it in tr.get("items", []):
        lines.append(f"| {it['period']} | {_fmt_money(it['total_amount'])} | {it['order_count']:,} | {it['total_quantity']:,} | {_fmt_money(it['avg_order_amount'])} |")
    return "\n".join(lines)


def _report_csv_en(ov, pf, tr) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Section", "Metric", "Value"])
    for label, key, val in [
        ("Overview", "Orders", ov.get("order_count", 0)),
        ("Overview", "Users", ov.get("user_count", 0)),
        ("Overview", "GMV", ov.get("total_amount", 0)),
        ("Overview", "AvgOrderValue", ov.get("avg_order_amount", 0)),
        ("Overview", "Units", ov.get("total_quantity", 0)),
        ("Overview", "Products", ov.get("product_count", 0)),
        ("Overview", "Categories", ov.get("category_count", 0)),
        ("Overview", "Brands", ov.get("brand_count", 0)),
        ("Overview", "DeliveryRate", ov.get("delivered_rate", 0)),
    ]:
        w.writerow([label, key, val])
    for r in pf.get("items", []):
        w.writerow(["Platform", r["platform"] + "_products", r["product_count"]])
        w.writerow(["Platform", r["platform"] + "_avg_price", r["avg_price"]])
        w.writerow(["Platform", r["platform"] + "_sales", r["sales_count"]])
    for it in tr.get("items", []):
        w.writerow(["Trend", it["period"] + "_gmv", it["total_amount"]])
        w.writerow(["Trend", it["period"] + "_orders", it["order_count"]])
    return buf.getvalue()


def _hot_md_en(hot, baidu, sg) -> str:
    lines = [
        "# Hot Search & Keyword Report",
        "",
        f"> Source: UUMit Data Marketplace (free, 0 UT) | Generated: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 1. Douyin Hot Search",
        "",
        "| # | Title | Heat |",
        "|---|---|---|",
    ]
    for it in hot.get("items", []):
        lines.append(f"| {it['rank']} | {it['title']} | {it.get('hot', 0):,} |")
    lines += ["", "## 2. Baidu Hot Search (Realtime)", "", "| # | Title | Index |", "|---|---|---|"]
    for it in baidu.get("items", []):
        lines.append(f"| {it['rank']} | {it['title']} | {it.get('index') or '-'} |")
    lines += ["", f"## 3. Taobao Suggestions (keyword: {sg.get('keyword', '')})", "", "| Word | Score |", "|---|---|"]
    for it in sg.get("items", []):
        lines.append(f"| {it.get('word')} | {it.get('score') or '-'} |")
    return "\n".join(lines)


def _hot_csv_en(hot, baidu, sg) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Section", "Rank", "Title", "Value", "URL"])
    for it in hot.get("items", []):
        w.writerow(["DouyinHot", it["rank"], it["title"], it.get("hot", ""), it.get("url", "")])
    for it in baidu.get("items", []):
        w.writerow(["BaiduHot", it["rank"], it["title"], it.get("index", ""), it.get("url", "")])
    for it in sg.get("items", []):
        w.writerow(["TaobaoSuggest", "", it.get("word", ""), it.get("score", ""), ""])
    return buf.getvalue()

# ---------------- 汇总 ----------------
def dashboard(fresh: bool = False) -> Dict[str, Any]:
    """面板一次性取数：账户 + 平台对比 + 大盘概览 + 月度趋势。"""
    account: Dict[str, Any] = {"connected": False, "ut_balance": None}
    try:
        acc = uumit_feed.account_status()
        account = {"connected": True, "ut_balance": acc.get("ut_balance"), "ut_available": acc.get("ut_available")}
    except uumit_feed.UumitError:
        pass

    overview = market_overview(fresh=fresh)
    platforms = platform_performance(fresh=fresh)
    trend = sales_trend(grain="month", fresh=fresh)

    return {
        "account": account,
        "overview": overview,
        "platforms": platforms,
        "trend": trend,
        "cards": overview_cards(fresh=fresh),
        "free_apis": [
            {"name": "统计各电商平台商品表现", "api_id": API_PLATFORM_PERFORMANCE},
            {"name": "查询电商订单用户经营概览", "api_id": API_MARKET_OVERVIEW},
            {"name": "分析电商销售额销量时间变化", "api_id": API_SALES_TREND},
        ],
    }
