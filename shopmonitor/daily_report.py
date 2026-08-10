# -*- coding: utf-8 -*-
"""日报自动摘要：大盘 + 热搜 + 今日告警 + 监控概况 -> Markdown，落盘 + 推送 Webhook。

- 每天最多生成一份（data/daily-reports/YYYY-MM-DD.md），幂等；
- Webhook 兼容企业微信/钉钉/飞书机器人（msgtype=markdown）；
- UUMit 数据不可用时自动降级（跳过对应小节并注明），不阻塞日报。
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from . import cache, uumit_data
from .config import ALERT_WEBHOOK_URL, DATA_DIR

REPORT_DIR = Path(DATA_DIR) / "daily-reports"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _fmt_money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "-"
    if v >= 1e8:
        return f"{v / 1e8:.2f} 亿"
    if v >= 1e4:
        return f"{v / 1e4:.1f} 万"
    return f"{v:,.2f}"


def _fmt_num(v) -> str:
    try:
        v = int(float(v or 0))
    except (TypeError, ValueError):
        return "-"
    return f"{v:,}"


def build_daily_report() -> str:
    """组装日报 Markdown。"""
    now = datetime.now()
    lines = [
        "# 电商监控日报",
        "",
        f"> 日期：{now.strftime('%Y-%m-%d %H:%M')}｜来源：本地监控 + UUMit 免费数据（0 扣费）",
        "",
    ]

    # 一、监控概况
    watches = cache.list_watches()
    enabled = [w for w in watches if w["enabled"]]
    today_alerts = [a for a in cache.list_alerts(limit=200) if (a.get("created_at") or "").startswith(_today())]
    lines += [
        "## 一、监控概况",
        "",
        f"- 关注项：{len(watches)} 个（启用 {len(enabled)}）",
        f"- 今日告警：{len(today_alerts)} 条",
        f"- 未读告警：{cache.unread_alert_count()} 条",
        "",
    ]

    # 二、大盘数据（UUMit 免费）
    try:
        ov = uumit_data.market_overview()
        pf = uumit_data.platform_performance()
        lines += [
            "## 二、电商大盘（UUMit 免费）",
            "",
            "| 指标 | 数值 | 指标 | 数值 |",
            "|---|---|---|---|",
            f"| 订单数 | {_fmt_num(ov.get('order_count'))} | 成交额 | {_fmt_money(ov.get('total_amount'))} |",
            f"| 用户数 | {_fmt_num(ov.get('user_count'))} | 客单价 | {_fmt_money(ov.get('avg_order_amount'))} |",
            f"| 销量(件) | {_fmt_num(ov.get('total_quantity'))} | 发货率 | {ov.get('delivered_rate') * 100:.1f}%" if ov.get('delivered_rate') is not None else f"| 销量(件) | {_fmt_num(ov.get('total_quantity'))} | 发货率 | - |",
            "",
            "平台对比：",
            "",
            "| 平台 | 商品数 | 均价 | 销量 | 评分 |",
            "|---|---|---|---|---|",
        ]
        for r in pf.get("items", []):
            lines.append(f"| {r['platform']} | {_fmt_num(r['product_count'])} | {_fmt_money(r['avg_price'])} | {_fmt_num(r['sales_count'])} | {r['avg_rating'] if r.get('avg_rating') is not None else '-'} |")
        lines.append("")
    except Exception:  # noqa: BLE001
        lines += ["## 二、电商大盘（UUMit 免费）", "", "> UUMit 数据暂不可用，跳过。", ""]

    # 三、热搜（UUMit 免费）
    try:
        hot = uumit_data.douyin_hot()
        baidu = uumit_data.baidu_hot(type_="realtime")
        lines += ["## 三、热搜", "", "**抖音实时热搜 Top5**："]
        for it in hot.get("items", [])[:5]:
            lines.append(f"{it['rank']}. {it['title']}（热度 {_fmt_num(it.get('hot'))}）")
        lines.append("")
        lines.append("**百度热搜（实时）Top5**：")
        for it in baidu.get("items", [])[:5]:
            lines.append(f"{it['rank']}. {it['title']}")
        lines.append("")
    except Exception:  # noqa: BLE001
        lines += ["## 三、热搜", "", "> UUMit 热搜暂不可用，跳过。", ""]

    # 四、今日告警明细
    lines += ["## 四、今日告警明细", ""]
    if today_alerts:
        for a in today_alerts[:30]:
            lines.append(f"- [{a['severity']}] {a['title']}：{a['message']}")
        if len(today_alerts) > 30:
            lines.append(f"- …等共 {len(today_alerts)} 条")
    else:
        lines.append("今日暂无告警。")
    lines.append("")

    # 五、关注商品快照（含预估毛利）
    lines += ["## 五、关注商品快照（含预估毛利）", "",
              "> 预估毛利 = 售价×(1−平台佣金−其他1%−ACOS10%) − 售价×成本占比40% − 运费¥8（可在面板「潜力商品筛选」按平台调参）", "",
              "| 平台 | 商品 | 最新价 | 销量 | 排名 | 预估毛利 | 毛利率 |",
              "|---|---|---|---|---|---|---|"]
    try:
        snap = cache.watch_overview()
    except Exception:  # noqa: BLE001
        snap = []
    if snap:
        from .insights import estimate_item_profit
        for x in snap[:10]:
            est, margin = estimate_item_profit(x.get("price"), x.get("platform"), 0.4, 8.0, 0.10)
            title = (x.get("title") or x.get("product_id") or "-")
            title = title[:24] + ("…" if len(title) > 24 else "")
            price_txt = _fmt_money(x.get("price")) if x.get("price") is not None else "-"
            sales_txt = _fmt_num(x.get("sales")) if x.get("sales") is not None else "-"
            rank_txt = "第" + str(x.get("rank")) + "名" if x.get("rank") is not None else "-"
            profit_txt = f"{est:.2f}" if est is not None else "-"
            margin_txt = f"{margin}%" if margin is not None else "-"
            lines.append(f"| {x.get('platform')} | {title} | {price_txt} | {sales_txt} | {rank_txt} | {profit_txt} | {margin_txt} |")
        lines.append("")
    else:
        lines.append("暂无关注商品快照（先添加关注并运行巡检）。")
        lines.append("")

    lines.append("---")
    lines.append("由 ShopMonitor 自动生成")
    return "\n".join(lines)


def today_report_path() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR / f"{_today()}.md"


def get_today_report() -> Optional[str]:
    p = today_report_path()
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def _push_webhook(md: str) -> bool:
    """推送日报：Webhook / 邮件 / Telegram，任一成功即算推送成功。"""
    from .notify import send_notify
    r = send_notify("ShopMonitor 日报", md, markdown=True)
    return any(r.values())


def generate_daily_report(push: bool = True) -> Dict[str, Any]:
    """生成今日日报并落盘；push=True 时推送到 Webhook。返回状态。"""
    md = build_daily_report()
    p = today_report_path()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    pushed = _push_webhook(md) if push else False
    today_alerts = [a for a in cache.list_alerts(limit=200) if (a.get("created_at") or "").startswith(_today())]
    return {
        "date": _today(),
        "path": str(p),
        "pushed": pushed,
        "alerts_today": len(today_alerts),
        "watch_count": len(cache.list_watches()),
    }


def maybe_generate_daily_report(push: bool = True) -> Optional[Dict[str, Any]]:
    """当天已生成则跳过，否则生成（幂等，供定时巡检调用）。"""
    p = today_report_path()
    if p.exists():
        return None
    return generate_daily_report(push=push)

# ---------------- 周期报告（周报/月报） ----------------
PERIOD_DIR = Path(DATA_DIR) / "period-reports"


def period_report_path(period: str = "week") -> Path:
    now = datetime.now()
    if period == "month":
        name = f"月报-{now.strftime('%Y-%m')}.md"
    else:
        iso = now.isocalendar()
        name = f"周报-{now.year}-W{iso[1]:02d}.md"
    PERIOD_DIR.mkdir(parents=True, exist_ok=True)
    return PERIOD_DIR / name


def build_period_report(period: str = "week") -> str:
    """周报/月报：告警统计 + 关注商品涨跌 Top + 热搜 + 大盘概览。"""
    from collections import Counter
    from datetime import timedelta

    days = 30 if period == "month" else 7
    label = "月报" if period == "month" else "周报"
    now = datetime.now()
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    lines = [f"# 电商监控{label}", "", f"> 周期：近 {days} 天（自 {since}）｜来源：本地监控 + UUMit 免费数据（0 扣费）", ""]

    # 一、告警统计
    alerts = cache.list_alerts(limit=1000)
    in_range = [a for a in alerts if (a.get("created_at") or "")[:10] >= since]
    by_type = Counter((a.get("alert_type") or "其他") for a in in_range)
    lines += ["## 一、告警统计", "",
              f"- 本期告警：{len(in_range)} 条（{label.lower()}较历史请自行对比）", "",
              "| 类型 | 数量 |", "|---|---|"]
    if by_type:
        for k, v in by_type.most_common(10):
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("| （本期无告警） | 0 |")
    lines.append("")

    # 二、关注商品涨跌 Top（用最近监控快照）
    lines += ["## 二、关注商品动态 Top", "", "| 平台 | 商品 | 最新价 | 销量 | 排名 |", "|---|---|---|---|---|"]
    try:
        snap = cache.watch_overview()
        snap = sorted(snap, key=lambda x: -(x.get("sales") or 0))[:10]
        if snap:
            for x in snap:
                title = (x.get("title") or x.get("product_id") or "-")[:24]
                lines.append(
                    f"| {x.get('platform')} | {title} | {_fmt_money(x.get('price')) if x.get('price') is not None else '-'} "
                    f"| {_fmt_num(x.get('sales')) if x.get('sales') is not None else '-'} "
                    f"| {'第'+str(x.get('rank'))+'名' if x.get('rank') is not None else '-'} |"
                )
        else:
            lines.append("| （暂无关注商品，先添加关注并运行巡检） | - | - | - |")
    except Exception:  # noqa: BLE001
        lines.append("| （监控快照暂不可用） | - | - | - |")
    lines.append("")

    # 三、热搜 Top5
    lines += ["## 三、热搜 Top5", ""]
    try:
        hot = uumit_data.douyin_hot()
        for it in (hot.get("items") or [])[:5]:
            lines.append(f"{it.get('rank')}. {it.get('title')}（热度 {_fmt_num(it.get('hot'))}）")
    except Exception:  # noqa: BLE001
        lines.append("UUMit 热搜暂不可用。")
    lines.append("")

    # 四、大盘概览
    lines += ["## 四、大盘概览（UUMit 免费）", ""]
    try:
        ov = uumit_data.market_overview()
        lines.append(
            f"- 订单数 {_fmt_num(ov.get('order_count'))}｜成交额 {_fmt_money(ov.get('total_amount'))}｜"
            f"客单价 {_fmt_money(ov.get('avg_order_amount'))}｜发货率 "
            + (f"{ov.get('delivered_rate') * 100:.1f}%" if ov.get('delivered_rate') is not None else "-")
        )
    except Exception:  # noqa: BLE001
        lines.append("UUMit 大盘暂不可用。")
    lines.append("")
    lines.append("---")
    lines.append("由 ShopMonitor 自动生成")
    return "\n".join(lines)