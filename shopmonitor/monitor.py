"""定时监控引擎：关注列表 -> 周期采集 -> 对比上次快照 -> 生成告警 -> 入库/推送。

告警规则（阈值可在 config 调整）：
- target_price 达到目标价：现价跌破关注时设置的目标价（Keepa 风格）
- price_drop   降价：现价 <= 上次价 - 阈值（百分比或绝对值）
- price_up     涨价（info）
- stock_out    缺货/预售：库存状态变化
- rating_drop  评分下降 >= 阈值
- review_surge 新增评论数 >= 阈值
- sales_surge  销量新增 >= 阈值
- rank_change  排名变动 >= 阈值
- new_arrival  关键词榜新进 Top-N（首次建基线不告警）
"""
import json
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

from . import cache
from .collectors.base import CollectorError
from .collectors.registry import get_adapter
from .config import (
    ALERT_JSONL_PATH,
    ALERT_WEBHOOK_URL,
    MONITOR_ENABLED,
    MONITOR_INTERVAL_SEC,
    MONITOR_TOP_N,
    PRICE_DROP_THRESHOLD_ABS,
    PRICE_DROP_THRESHOLD_PCT,
    RANK_CHANGE_THRESHOLD,
    RATING_DROP_THRESHOLD,
    REVIEW_SURGE_THRESHOLD,
    SALES_SURGE_THRESHOLD,
)

_STOCK_BAD = {"缺货", "预售"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pct_change(now, before) -> Optional[float]:
    if now is None or before is None or not before:
        return None
    return (float(now) - float(before)) / float(before) * 100.0


class Monitor:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._last_run_at: Optional[str] = None
        self._last_summary: Optional[dict] = None

    # ---------------- 调度 ----------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="shopmonitor-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        interval = MONITOR_INTERVAL_SEC
        while not self._stop.wait(interval):
            try:
                self.run_once()
            except Exception:  # noqa: BLE001
                pass  # 单轮失败不影响下一轮

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict:
        return {
            "scheduler_running": self.running,
            "interval_sec": MONITOR_INTERVAL_SEC,
            "last_run_at": self._last_run_at,
            "last_summary": self._last_summary,
            "watch_count": len(cache.list_watches()),
            "unread_alerts": cache.unread_alert_count(),
        }

    # ---------------- 执行 ----------------
    def run_once(self) -> dict:
        watches = [w for w in cache.list_watches() if w["enabled"]]
        summary = {"watches": len(watches), "checked_items": 0, "alerts": 0, "errors": []}
        for w in watches:
            try:
                alerts, checked = self._check_watch(w)
                summary["alerts"] += len(alerts)
                summary["checked_items"] += checked
            except Exception as e:  # noqa: BLE001
                summary["errors"].append({"watch_id": w["id"], "error": str(e)[:200]})
        self._last_run_at = _now_iso()
        self._last_summary = summary
        # 每日自动生成日报（当天已生成则跳过；保存 + 推送到 Webhook）
        try:
            from .daily_report import maybe_generate_daily_report
            maybe_generate_daily_report()
        except Exception:  # noqa: BLE001
            pass
        return summary

    def _check_watch(self, w: dict) -> List[dict]:
        adapter = get_adapter(w["platform"])
        if w["mode"] == "product":
            items = self._fetch_product_items(adapter, w)
        else:
            items = self._fetch_rank_items(adapter, w)
        cache.touch_watch(w["id"])
        alerts: List[dict] = []
        seen: set = set()
        checked = 0
        # 关键词模式：是否已有基线（有基线后新出现的商品 = 新品上榜）
        has_baseline = w["mode"] == "keyword" and cache.watch_has_state(w["id"])
        for item in items:
            pid = item.product_id
            seen.add(pid)
            checked += 1
            cache.add_monitor_history(
                w["id"], pid, item.title, item.rank, item.price, item.sales, item.rating, item.review_count
            )
            state = cache.get_monitor_state(w["id"], pid)
            if state is None:
                # 首次见：已有基线则视为新品上榜；否则只建立基线不告警
                if has_baseline:
                    alerts.append(
                        self._make_alert(
                            w, item, "new_arrival", "新品上榜",
                            f"{item.title} 新进入 Top-{w['top_n']}（新出现在榜单）",
                            "info",
                        )
                    )
                cache.upsert_monitor_state(w["id"], pid, _snapshot(item))
                continue
            a = self._compare(w, item, state)
            alerts.extend(a)
            cache.upsert_monitor_state(w["id"], pid, _snapshot(item))
        # 关键词模式：上次在榜、这次掉出 Top-N -> 排名下滑提示
        if w["mode"] == "keyword":
            for stale in self._stale_items(w, seen):
                alerts.append(
                    self._make_alert(
                        w, stale, "rank_change", "掉出榜单",
                        f"{stale.get('title', stale['product_id'])} 已掉出 Top-{w['top_n']}",
                        "info",
                    )
                )
        for a in alerts:
            self._emit(a)
        return alerts, checked

    def _fetch_rank_items(self, adapter, w: dict) -> list:
        # 监控用真实数据：失败跳过（不降级到 mock，避免假告警）
        cat = w.get("category") or w.get("keyword")
        items = adapter.fetch_rank(category=cat, limit=w.get("top_n") or MONITOR_TOP_N)
        return items

    def _fetch_product_items(self, adapter, w: dict) -> list:
        pid = w.get("product_id")
        if not pid:
            return []
        try:
            p = adapter.fetch_product(pid)
            return [p]
        except CollectorError:
            cached = cache.get_product(w["platform"], pid)
            if cached:
                from .models import Product

                return [Product(**cached)]
            raise

    def _compare(self, w: dict, item, state: dict) -> List[dict]:
        alerts: List[dict] = []
        pid = item.product_id
        title = item.title or pid

        # 目标价提醒（Keepa 风格）：现价跌破用户设置的目标价即告警
        tp = w.get("target_price")
        if tp and item.price is not None and item.price <= float(tp):
            alerts.append(
                self._make_alert(
                    w, item, "target_price", "达到目标价",
                    f"{title} 现价 ¥{item.price:.2f} ≤ 目标价 ¥{float(tp):.2f}，可以入手",
                    "info",
                )
            )

        # 降价 / 涨价
        if item.price is not None and state.get("last_price") is not None:
            pct = _pct_change(item.price, state["last_price"])
            drop = state["last_price"] - item.price
            if pct is not None and pct <= -PRICE_DROP_THRESHOLD_PCT or drop >= PRICE_DROP_THRESHOLD_ABS:
                alerts.append(
                    self._make_alert(
                        w, item, "price_drop", "降价提醒",
                        f"{title} 由 ¥{state['last_price']:.2f} 降至 ¥{item.price:.2f}（-{abs(pct or 0):.1f}%）",
                        "warning",
                    )
                )
            elif pct is not None and pct >= PRICE_DROP_THRESHOLD_PCT:
                alerts.append(
                    self._make_alert(
                        w, item, "price_up", "涨价提醒",
                        f"{title} 由 ¥{state['last_price']:.2f} 涨至 ¥{item.price:.2f}（+{pct:.1f}%）",
                        "info",
                    )
                )

        # 缺货 / 预售
        if item.stock_status and state.get("last_stock") and item.stock_status != state["last_stock"]:
            if item.stock_status in _STOCK_BAD:
                alerts.append(
                    self._make_alert(
                        w, item, "stock_out", "库存告警",
                        f"{title} 库存变为「{item.stock_status}」（原「{state['last_stock']}」）",
                        "warning",
                    )
                )

        # 评分下降
        if item.rating is not None and state.get("last_rating") is not None:
            if state["last_rating"] - item.rating >= RATING_DROP_THRESHOLD:
                alerts.append(
                    self._make_alert(
                        w, item, "rating_drop", "评分下滑",
                        f"{title} 评分由 {state['last_rating']} 降至 {item.rating}",
                        "warning",
                    )
                )

        # 新增评论
        if item.review_count is not None and state.get("last_review_count") is not None:
            surge = item.review_count - state["last_review_count"]
            if surge >= REVIEW_SURGE_THRESHOLD:
                alerts.append(
                    self._make_alert(
                        w, item, "review_surge", "评论激增",
                        f"{title} 新增评论 {surge} 条（累计 {item.review_count}）",
                        "info",
                    )
                )

        # 销量激增
        if item.sales is not None and state.get("last_sales") is not None:
            surge = item.sales - state["last_sales"]
            if surge >= SALES_SURGE_THRESHOLD:
                alerts.append(
                    self._make_alert(
                        w, item, "sales_surge", "销量激增",
                        f"{title} 销量新增 {surge}（累计 {item.sales}）",
                        "info",
                    )
                )

        # 排名变动
        if item.rank is not None and state.get("last_rank") is not None:
            change = abs(item.rank - state["last_rank"])
            if change >= RANK_CHANGE_THRESHOLD:
                alerts.append(
                    self._make_alert(
                        w, item, "rank_change", "排名变动",
                        f"{title} 排名 {state['last_rank']} -> {item.rank}",
                        "info",
                    )
                )
        return alerts

    def _stale_items(self, w: dict, seen: set) -> List[dict]:
        """上次在榜、这次不在 Top-N 的商品（仅关键词模式）。"""
        c = cache._conn()
        rows = c.execute(
            "SELECT product_id, last_rank, last_price, last_sales FROM monitor_state WHERE watch_id=?",
            (w["id"],),
        ).fetchall()
        c.close()
        out = []
        for pid, rank, price, sales in rows:
            if pid not in seen:
                out.append({"product_id": pid, "title": pid, "last_rank": rank, "last_price": price, "last_sales": sales})
        return out

    def _make_alert(self, w: dict, item, alert_type: str, title: str, message: str, severity: str) -> dict:
        return {
            "watch_id": w["id"],
            "platform": w["platform"],
            "product_id": item.product_id,
            "title": title,
            "message": message,
            "alert_type": alert_type,
            "severity": severity,
        }

    def _emit(self, a: dict) -> None:
        aid = cache.add_alert(
            a["watch_id"], a["platform"], a["product_id"], a["title"], a["message"],
            a["alert_type"], a["severity"],
        )
        # JSONL 落盘
        try:
            with open(ALERT_JSONL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({**a, "id": aid, "created_at": _now_iso()}, ensure_ascii=False) + "\n")
        except OSError:
            pass
        # 多通道推送（Webhook / 邮件 / Telegram，任一配好即通知）
        try:
            from ..notify import send_notify
            send_notify(
                f"【ShopMonitor 告警】{a['title']}",
                f"{a['message']}\n平台: {a['platform']} 商品: {a['product_id']}",
            )
        except Exception:  # noqa: BLE001
            pass

    def _webhook(self, a: dict) -> None:
        import urllib.request

        payload = json.dumps(
            {
                "msgtype": "text",
                "text": {"content": f"【ShopMonitor 告警】{a['title']}\n{a['message']}\n平台: {a['platform']} 商品: {a['product_id']}"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            req = urllib.request.Request(
                ALERT_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:  # noqa: BLE001
            pass


def _snapshot(item) -> dict:
    return {
        "last_price": item.price,
        "last_sales": item.sales,
        "last_rating": item.rating,
        "last_review_count": item.review_count,
        "last_stock": item.stock_status,
        "last_rank": item.rank,
    }


# 全局单例（供 run_api 与 API 路由共用）
monitor = Monitor()