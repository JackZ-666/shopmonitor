"""SQLite 缓存：榜单缓存 / 商品快照 / 价格销量历史 / 监控关注 / 监控状态 / 告警。"""
import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import List, Optional

from .config import DB_PATH
from .models import HistoryPoint, Product


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_history_columns(c: sqlite3.Connection) -> None:
    cols = {r[1] for r in c.execute("PRAGMA table_info(history)").fetchall()}
    for name, ddl in (
        ("rating", "ALTER TABLE history ADD COLUMN rating REAL"),
        ("review_count", "ALTER TABLE history ADD COLUMN review_count INTEGER"),
    ):
        if name not in cols:
            try:
                c.execute(ddl)
            except sqlite3.OperationalError:
                pass
    c.commit()


def _ensure_watch_columns(c: sqlite3.Connection) -> None:
    cols = {r[1] for r in c.execute("PRAGMA table_info(watchlist)").fetchall()}
    if "target_price" not in cols:
        try:
            c.execute("ALTER TABLE watchlist ADD COLUMN target_price REAL")
        except sqlite3.OperationalError:
            pass
    c.commit()


def init_db() -> None:
    c = _conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS rank_cache (
            platform TEXT NOT NULL,
            category TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (platform, category)
        );
        CREATE TABLE IF NOT EXISTS products (
            platform TEXT NOT NULL,
            product_id TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (platform, product_id)
        );
        CREATE TABLE IF NOT EXISTS history (
            platform TEXT NOT NULL,
            product_id TEXT NOT NULL,
            price REAL,
            sales INTEGER,
            rating REAL,
            review_count INTEGER,
            crawled_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_history ON history(platform, product_id, crawled_at);

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'keyword',
            keyword TEXT,
            category TEXT,
            product_id TEXT,
            alias TEXT,
            top_n INTEGER DEFAULT 10,
            target_price REAL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT,
            last_checked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS monitor_state (
            watch_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            last_price REAL,
            last_sales INTEGER,
            last_rating REAL,
            last_review_count INTEGER,
            last_stock TEXT,
            last_rank INTEGER,
            updated_at TEXT,
            PRIMARY KEY (watch_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id INTEGER,
            platform TEXT,
            product_id TEXT,
            title TEXT,
            message TEXT,
            alert_type TEXT,
            severity TEXT,
            created_at TEXT,
            is_read INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);

        CREATE TABLE IF NOT EXISTS monitor_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            title TEXT,
            rank INTEGER,
            price REAL,
            sales INTEGER,
            rating REAL,
            review_count INTEGER,
            checked_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_monitor_history ON monitor_history(watch_id, checked_at);

        CREATE TABLE IF NOT EXISTS hot_history (
            platform TEXT NOT NULL,
            word TEXT NOT NULL,
            heat REAL,
            rank INTEGER,
            captured_at TEXT NOT NULL,
            PRIMARY KEY (platform, word, captured_at)
        );
        CREATE INDEX IF NOT EXISTS idx_hot_history ON hot_history(platform, captured_at);

        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            product_id TEXT NOT NULL,
            title TEXT,
            price REAL,
            status TEXT DEFAULT '考察中',
            note TEXT,
            keyword TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_picks_created ON picks(created_at);

        CREATE TABLE IF NOT EXISTS rank_snapshots (
            platform TEXT NOT NULL,
            category TEXT NOT NULL,
            captured_date TEXT NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY (platform, category, captured_date)
        );
        """
    )
    c.commit()
    _ensure_history_columns(c)
    _ensure_watch_columns(c)
    c.close()


# ---------------- 榜单缓存 ----------------
def get_rank_cache(platform: str, category: str, ttl: int) -> Optional[dict]:
    c = _conn()
    row = c.execute(
        "SELECT payload, created_at FROM rank_cache WHERE platform=? AND category=?",
        (platform, category or ""),
    ).fetchone()
    c.close()
    if not row:
        return None
    payload, created_at = row
    if time.time() - created_at > ttl:
        return None
    return json.loads(payload)


def set_rank_cache(platform: str, category: str, payload: dict) -> None:
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO rank_cache(platform, category, payload, created_at) VALUES(?,?,?,?)",
        (platform, category or "", json.dumps(payload, ensure_ascii=False), time.time()),
    )
    c.commit()
    c.close()


# ---------------- 商品快照 ----------------
def upsert_product(p: Product) -> None:
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO products(platform, product_id, snapshot, updated_at) VALUES(?,?,?,?)",
        (p.platform, p.product_id, p.model_dump_json(), time.time()),
    )
    c.commit()
    c.close()


def get_product(platform: str, product_id: str) -> Optional[dict]:
    c = _conn()
    row = c.execute(
        "SELECT snapshot FROM products WHERE platform=? AND product_id=?",
        (platform, product_id),
    ).fetchone()
    c.close()
    return json.loads(row[0]) if row else None


# ---------------- 价格/销量历史 ----------------
def save_history(
    platform: str,
    product_id: str,
    price: Optional[float],
    sales: Optional[int],
    rating: Optional[float] = None,
    review_count: Optional[int] = None,
) -> None:
    c = _conn()
    _ensure_history_columns(c)
    c.execute(
        "INSERT INTO history(platform, product_id, price, sales, rating, review_count, crawled_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (platform, product_id, price, sales, rating, review_count, _iso()),
    )
    c.commit()
    c.close()


def get_history(platform: str, product_id: str, limit: int = 30) -> List[HistoryPoint]:
    c = _conn()
    _ensure_history_columns(c)
    rows = c.execute(
        "SELECT price, sales, rating, review_count, crawled_at FROM history "
        "WHERE platform=? AND product_id=? ORDER BY crawled_at DESC LIMIT ?",
        (platform, product_id, limit),
    ).fetchall()
    c.close()
    return [HistoryPoint(price=r[0], sales=r[1], rating=r[2], review_count=r[3], crawled_at=r[4]) for r in rows]


def latest_history(platform: str, product_id: str) -> Optional[HistoryPoint]:
    rows = get_history(platform, product_id, 1)
    return rows[0] if rows else None


# ---------------- 监控：关注列表 ----------------
def add_watch(
    platform: str,
    mode: str = "keyword",
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    product_id: Optional[str] = None,
    alias: Optional[str] = None,
    top_n: int = 10,
    target_price: Optional[float] = None,
    enabled: bool = True,
) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO watchlist(platform, mode, keyword, category, product_id, alias, top_n, target_price, enabled, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (platform, mode, keyword, category, product_id, alias, top_n, target_price, 1 if enabled else 0, _iso()),
    )
    c.commit()
    wid = cur.lastrowid
    c.close()
    return wid


def list_watches() -> List[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT id, platform, mode, keyword, category, product_id, alias, top_n, target_price, enabled, created_at, last_checked_at "
        "FROM watchlist ORDER BY id"
    ).fetchall()
    c.close()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0], "platform": r[1], "mode": r[2], "keyword": r[3], "category": r[4],
                "product_id": r[5], "alias": r[6], "top_n": r[7], "target_price": r[8], "enabled": bool(r[9]),
                "created_at": r[10], "last_checked_at": r[11],
            }
        )
    return out


def get_watch(watch_id: int) -> Optional[dict]:
    for w in list_watches():
        if w["id"] == watch_id:
            return w
    return None


def delete_watch(watch_id: int) -> bool:
    c = _conn()
    cur = c.execute("DELETE FROM watchlist WHERE id=?", (watch_id,))
    c.execute("DELETE FROM monitor_state WHERE watch_id=?", (watch_id,))
    c.commit()
    ok = cur.rowcount > 0
    c.close()
    return ok


def toggle_watch(watch_id: int) -> Optional[dict]:
    w = get_watch(watch_id)
    if not w:
        return None
    c = _conn()
    c.execute("UPDATE watchlist SET enabled=? WHERE id=?", (0 if w["enabled"] else 1, watch_id))
    c.commit()
    c.close()
    return get_watch(watch_id)


def touch_watch(watch_id: int) -> None:
    c = _conn()
    c.execute("UPDATE watchlist SET last_checked_at=? WHERE id=?", (_iso(), watch_id))
    c.commit()
    c.close()


# ---------------- 监控：状态（上次快照） ----------------
def get_monitor_state(watch_id: int, product_id: str) -> Optional[dict]:
    c = _conn()
    row = c.execute(
        "SELECT last_price, last_sales, last_rating, last_review_count, last_stock, last_rank, updated_at "
        "FROM monitor_state WHERE watch_id=? AND product_id=?",
        (watch_id, product_id),
    ).fetchone()
    c.close()
    if not row:
        return None
    return {
        "last_price": row[0], "last_sales": row[1], "last_rating": row[2],
        "last_review_count": row[3], "last_stock": row[4], "last_rank": row[5], "updated_at": row[6],
    }


def upsert_monitor_state(watch_id: int, product_id: str, state: dict) -> None:
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO monitor_state(watch_id, product_id, last_price, last_sales, last_rating, "
        "last_review_count, last_stock, last_rank, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            watch_id, product_id, state.get("last_price"), state.get("last_sales"),
            state.get("last_rating"), state.get("last_review_count"), state.get("last_stock"),
            state.get("last_rank"), _iso(),
        ),
    )
    c.commit()
    c.close()


# ---------------- 监控：告警 ----------------
def add_alert(
    watch_id: int,
    platform: str,
    product_id: str,
    title: str,
    message: str,
    alert_type: str,
    severity: str = "info",
) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO alerts(watch_id, platform, product_id, title, message, alert_type, severity, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (watch_id, platform, product_id, title, message, alert_type, severity, _iso()),
    )
    c.commit()
    aid = cur.lastrowid
    c.close()
    return aid


def list_alerts(limit: int = 50, unread_only: bool = False) -> List[dict]:
    c = _conn()
    sql = "SELECT id, watch_id, platform, product_id, title, message, alert_type, severity, created_at, is_read FROM alerts"
    if unread_only:
        sql += " WHERE is_read=0"
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    rows = c.execute(sql, (limit,)).fetchall()
    c.close()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0], "watch_id": r[1], "platform": r[2], "product_id": r[3], "title": r[4],
                "message": r[5], "alert_type": r[6], "severity": r[7], "created_at": r[8], "is_read": bool(r[9]),
            }
        )
    return out


def unread_alert_count() -> int:
    c = _conn()
    row = c.execute("SELECT COUNT(*) FROM alerts WHERE is_read=0").fetchone()
    c.close()
    return row[0]


def mark_alerts_read(ids: Optional[List[int]] = None) -> int:
    c = _conn()
    if ids:
        marks = ",".join("?" * len(ids))
        cur = c.execute(f"UPDATE alerts SET is_read=1 WHERE id IN ({marks})", ids)
    else:
        cur = c.execute("UPDATE alerts SET is_read=1")
    c.commit()
    n = cur.rowcount
    c.close()
    return n


# ---------------- 监控：历史排名快照（排名趋势图数据源） ----------------
def add_monitor_history(watch_id: int, product_id: str, title: str, rank, price, sales, rating, review_count) -> None:
    """每次巡检追加一条快照（不覆盖，保留全部历史）。"""
    c = _conn()
    c.execute(
        "INSERT INTO monitor_history(watch_id, product_id, title, rank, price, sales, rating, review_count, checked_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (watch_id, product_id, title, rank, price, sales, rating, review_count, _iso()),
    )
    c.commit()
    c.close()


def get_monitor_history(watch_id: int, limit: int = 300) -> List[dict]:
    """按时间升序返回某关注项的历史快照（rank/price/sales/rating）。"""
    c = _conn()
    rows = c.execute(
        "SELECT product_id, title, rank, price, sales, rating, review_count, checked_at "
        "FROM monitor_history WHERE watch_id=? ORDER BY checked_at ASC, id ASC",
        (watch_id,),
    ).fetchall()
    c.close()
    out = []
    for r in rows[-limit:]:
        out.append(
            {
                "product_id": r[0], "title": r[1], "rank": r[2], "price": r[3], "sales": r[4],
                "rating": r[5], "review_count": r[6], "checked_at": r[7],
            }
        )
    return out


def list_monitor_products(watch_id: int) -> List[dict]:
    """某关注项近期监控到的商品（去重，含最新标题/最近排名）。"""
    c = _conn()
    rows = c.execute(
        "SELECT product_id, title, rank, MAX(checked_at) FROM monitor_history "
        "WHERE watch_id=? GROUP BY product_id ORDER BY MAX(checked_at) DESC",
        (watch_id,),
    ).fetchall()
    c.close()
    return [
        {"product_id": r[0], "title": r[1], "rank": r[2], "last_checked_at": r[3]}
        for r in rows
    ]


# ---------------- 监控：今日变动榜（对标 Keepa 价格变动榜） ----------------
def recent_movers(limit: int = 10) -> dict:
    """从监控快照计算 降价榜/涨价榜/销量飙升榜（各取最近两次快照对比）。"""
    c = _conn()
    rows = c.execute(
        "SELECT watch_id, product_id, title, rank, price, sales, checked_at "
        "FROM monitor_history ORDER BY checked_at ASC, id ASC"
    ).fetchall()
    c.close()
    watches = {w["id"]: w for w in list_watches()}

    # 按 (watch_id, product_id) 分组，取最近两条
    groups: dict = {}
    for r in rows:
        key = (r[0], r[1])
        groups.setdefault(key, []).append(
            {"title": r[2], "rank": r[3], "price": r[4], "sales": r[5], "checked_at": r[6]}
        )

    movers = []
    for (watch_id, pid), recs in groups.items():
        if len(recs) < 2:
            continue
        a, b = recs[-2], recs[-1]  # a=上次 b=最新
        w = watches.get(watch_id, {})
        title = b.get("title") or pid
        price_pct = None
        if a["price"] and b["price"] is not None and a["price"]:
            price_pct = (b["price"] - a["price"]) / a["price"] * 100
        sales_delta = None
        if a["sales"] is not None and b["sales"] is not None:
            sales_delta = b["sales"] - a["sales"]
        rank_delta = None
        if a["rank"] is not None and b["rank"] is not None:
            rank_delta = a["rank"] - b["rank"]  # 正=名次上升
        movers.append(
            {
                "watch_id": watch_id,
                "platform": w.get("platform", ""),
                "keyword": w.get("keyword") or w.get("category") or "",
                "product_id": pid,
                "title": title,
                "price_before": round(a["price"], 2) if a["price"] is not None else None,
                "price_now": round(b["price"], 2) if b["price"] is not None else None,
                "price_change_pct": round(price_pct, 2) if price_pct is not None else None,
                "sales_before": a["sales"],
                "sales_now": b["sales"],
                "sales_delta": sales_delta,
                "rank_before": a["rank"],
                "rank_now": b["rank"],
                "rank_delta": rank_delta,
                "checked_at": b["checked_at"],
            }
        )

    # 排序分类
    drops = sorted(
        [m for m in movers if m["price_change_pct"] is not None and m["price_change_pct"] <= -0.5],
        key=lambda x: x["price_change_pct"],
    )[:limit]
    rises = sorted(
        [m for m in movers if m["price_change_pct"] is not None and m["price_change_pct"] >= 0.5],
        key=lambda x: -x["price_change_pct"],
    )[:limit]
    surges = sorted(
        [m for m in movers if m["sales_delta"] is not None and m["sales_delta"] > 0],
        key=lambda x: -x["sales_delta"],
    )[:limit]
    return {"drops": drops, "rises": rises, "sales_surges": surges, "total_compared": len(movers)}


# ---------------- 监控：关注商品总览（对标知虾监控中心） ----------------
def watch_overview() -> list:
    """所有启用关注项下的商品最新状态（价格/销量/排名/库存），供总览表。"""
    c = _conn()
    rows = c.execute(
        "SELECT w.id, w.platform, w.keyword, w.category, w.alias, w.target_price, "
        "       s.product_id, s.last_price, s.last_sales, s.last_rank, s.last_stock, s.updated_at, "
        "       p.snapshot "
        "FROM watchlist w "
        "LEFT JOIN monitor_state s ON w.id = s.watch_id "
        "LEFT JOIN products p ON p.platform = w.platform AND p.product_id = s.product_id "
        "WHERE w.enabled = 1 ORDER BY w.id, s.product_id"
    ).fetchall()
    c.close()
    out = []
    for r in rows:
        title = ""
        if r[12]:
            try:
                title = (json.loads(r[12]) or {}).get("title", "")
            except (ValueError, TypeError):
                title = ""
        out.append(
            {
                "watch_id": r[0],
                "platform": r[1],
                "keyword": r[2] or r[3] or r[4] or "",
                "target_price": r[5],
                "product_id": r[6],
                "title": title,
                "price": r[7],
                "sales": r[8],
                "rank": r[9],
                "stock": r[10],
                "updated_at": r[11],
            }
        )
    return out


# ---------------- 热搜快照（热搜词热度趋势） ----------------
def record_hot_snapshot(platform: str, items: list) -> None:
    """记录当日热搜快照（同平台同日同词覆盖更新）。items: [{word, heat, rank}]"""
    day = datetime.now().strftime("%Y-%m-%d")
    c = _conn()
    for it in items:
        word = (it.get("word") or "").strip()
        if not word:
            continue
        c.execute(
            "INSERT INTO hot_history(platform, word, heat, rank, captured_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(platform, word, captured_at) DO UPDATE SET heat=excluded.heat, rank=excluded.rank",
            (platform, word, it.get("heat"), it.get("rank"), day),
        )
    c.commit()
    c.close()


def hot_trend(platform: str, days: int = 7, limit: int = 10) -> dict:
    """热搜词热度趋势：返回近 N 天各词的 最新热度/首日热度/变化/排名。"""
    from datetime import timedelta

    start = (datetime.now() - timedelta(days=max(days - 1, 0))).strftime("%Y-%m-%d")
    c = _conn()
    rows = c.execute(
        "SELECT word, heat, rank, captured_at FROM hot_history "
        "WHERE platform=? AND captured_at>=? ORDER BY captured_at ASC",
        (platform, start),
    ).fetchall()
    c.close()
    by_word: dict = {}
    for word, heat, rank, day in rows:
        by_word.setdefault(word, []).append({"heat": heat, "rank": rank, "day": day})
    out = []
    for word, series in by_word.items():
        first, last = series[0], series[-1]
        change_pct = None
        if first["heat"] and last["heat"] is not None:
            change_pct = round((last["heat"] - first["heat"]) / first["heat"] * 100, 1)
        out.append(
            {
                "word": word,
                "days": len(series),
                "first_heat": first["heat"],
                "latest_heat": last["heat"],
                "change_pct": change_pct,
                "latest_rank": last["rank"],
                "series": series,
            }
        )
    out.sort(key=lambda x: -(x["latest_heat"] or 0))
    return {"platform": platform, "days": days, "count": len(out), "items": out[:limit]}


# ---------------- 监控：新品上榜（竞品上新监控） ----------------
def watch_has_state(watch_id: int) -> bool:
    """该关注项是否已有基线快照（用于判断"新品上榜"）。"""
    c = _conn()
    row = c.execute("SELECT COUNT(*) FROM monitor_state WHERE watch_id=?", (watch_id,)).fetchone()
    c.close()
    return bool(row and row[0] > 0)


def recent_new_arrivals(days: int = 3, limit: int = 20) -> list:
    """近期首次出现在监控榜中的商品（新品上榜）。"""
    from datetime import timedelta

    since = (datetime.now() - timedelta(days=max(days - 1, 0))).strftime("%Y-%m-%d")
    c = _conn()
    rows = c.execute(
        "SELECT watch_id, product_id, MIN(checked_at) AS first_seen "
        "FROM monitor_history GROUP BY watch_id, product_id HAVING first_seen >= ? "
        "ORDER BY first_seen DESC LIMIT ?",
        (since, limit),
    ).fetchall()
    c.close()
    watches = {w["id"]: w for w in list_watches()}
    out = []
    for watch_id, pid, first_seen in rows:
        w = watches.get(watch_id, {})
        out.append(
            {
                "watch_id": watch_id,
                "platform": w.get("platform", ""),
                "keyword": w.get("keyword") or w.get("category") or "",
                "product_id": pid,
                "first_seen": first_seen,
            }
        )
    return out

# ---------------- 选品库（收藏/备选管理） ----------------
_PICK_STATUS = ("考察中", "可上架", "已上架", "放弃")


def add_pick(platform: str, product_id: str, title: str = "", price=None,
             status: str = "考察中", note: str = "", keyword: str = "") -> int:
    """加入选品库，返回 id；同平台+商品已存在则更新并返回原 id。"""
    status = status if status in _PICK_STATUS else "考察中"
    now = _iso()
    c = _conn()
    row = c.execute(
        "SELECT id FROM picks WHERE platform=? AND product_id=?", (platform, str(product_id))
    ).fetchone()
    if row:
        pid = int(row[0])
        c.execute(
            "UPDATE picks SET title=?, price=?, status=?, note=?, keyword=?, updated_at=? WHERE id=?",
            (title, price, status, note, keyword, now, pid),
        )
        c.commit()
        c.close()
        return pid
    c.execute(
        "INSERT INTO picks(platform, product_id, title, price, status, note, keyword, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (platform, str(product_id), title, price, status, note, keyword, now, now),
    )
    c.commit()
    pid = int(c.execute("SELECT id FROM picks ORDER BY id DESC LIMIT 1").fetchone()[0])
    c.close()
    return pid


def list_picks(status: Optional[str] = None) -> list:
    c = _conn()
    if status:
        rows = c.execute(
            "SELECT id, platform, product_id, title, price, status, note, keyword, created_at, updated_at "
            "FROM picks WHERE status=? ORDER BY updated_at DESC", (status,)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT id, platform, product_id, title, price, status, note, keyword, created_at, updated_at "
            "FROM picks ORDER BY updated_at DESC"
        ).fetchall()
    c.close()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "platform": r[1], "product_id": r[2], "title": r[3] or "",
            "price": r[4], "status": r[5] or "考察中", "note": r[6] or "",
            "keyword": r[7] or "", "created_at": r[8], "updated_at": r[9],
        })
    return out


def update_pick(pick_id: int, status: Optional[str] = None, note: Optional[str] = None) -> bool:
    c = _conn()
    cur = c.execute("SELECT id FROM picks WHERE id=?", (pick_id,)).fetchone()
    if not cur:
        c.close()
        return False
    sets = []
    vals = []
    if status:
        sets.append("status=?")
        vals.append(status if status in _PICK_STATUS else "考察中")
    if note is not None:
        sets.append("note=?")
        vals.append(note)
    sets.append("updated_at=?")
    vals.append(_iso())
    vals.append(pick_id)
    c.execute(f"UPDATE picks SET {', '.join(sets)} WHERE id=?", vals)
    c.commit()
    c.close()
    return True


def delete_pick(pick_id: int) -> bool:
    c = _conn()
    c.execute("DELETE FROM picks WHERE id=?", (pick_id,))
    c.commit()
    ok = c.total_changes > 0
    c.close()
    return ok


def pick_count() -> int:
    c = _conn()
    n = c.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    c.close()
    return int(n)

# ---------------- 榜单历史快照（类目榜单趋势） ----------------
def record_rank_snapshot(platform: str, category: str, items) -> None:
    """每日一次：记录类目榜单快照（商品数/均价/Top ID），用于榜单历史趋势。"""
    if not items:
        return
    date = datetime.now().strftime("%Y-%m-%d")
    ids, prices = [], []
    for i in items:
        if isinstance(i, dict):
            pid = str(i.get("product_id") or "")
            p = i.get("price")
        else:
            pid = str(getattr(i, "product_id", "") or "")
            p = getattr(i, "price", None)
        if pid:
            ids.append(pid)
        if p is not None:
            try:
                prices.append(float(p))
            except (TypeError, ValueError):
                pass
    payload = json.dumps({
        "count": len(ids),
        "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        "ids": ids[:50],
    }, ensure_ascii=False)
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO rank_snapshots(platform, category, captured_date, payload) VALUES(?,?,?,?)",
        (platform, category or "", date, payload),
    )
    c.commit()
    c.close()


def rank_snapshot_trend(platform: str, category: str, days: int = 7) -> dict:
    """近 N 天榜单快照趋势：每日商品数/均价/新品数（对比前一天）。"""
    c = _conn()
    rows = c.execute(
        "SELECT captured_date, payload FROM rank_snapshots "
        "WHERE platform=? AND category=? AND captured_date >= date('now', ?) ORDER BY captured_date",
        (platform, category or "", f"-{int(days)} days"),
    ).fetchall()
    c.close()
    items = []
    prev_ids = set()
    for date, payload in rows:
        try:
            d = json.loads(payload)
        except (ValueError, TypeError):
            continue
        ids = set(d.get("ids") or [])
        new_count = len(ids - prev_ids)
        items.append({
            "date": date,
            "count": d.get("count", 0),
            "avg_price": d.get("avg_price"),
            "new_count": new_count,
            "new_rate": round(new_count / len(ids) * 100, 1) if ids else 0,
        })
        prev_ids = ids
    return {"platform": platform, "category": category or "", "items": items}
