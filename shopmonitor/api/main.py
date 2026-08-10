"""ShopMonitor API：全平台选品/竞品监控 + UUMit 免费数据源。

接口提供中英双路径：
- 英文路径：/api/v1/rank/{platform}（兼容程序/Agent 调用）
- 中文路径：/api/v1/榜单/{platform}（方便人直接看懂）
所有接口在 /docs 与 OpenAPI 中均显示中文名。
"""
import hashlib
import hmac
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .. import cache, uumit_data, uumit_feed
from ..collectors.base import CollectorError
from ..collectors.mock import MockAdapter
from ..collectors.registry import get_adapter, list_platforms
from ..config import ALLOW_MOCK_FALLBACK, DEFAULT_RANK_TTL, SHOPMONITOR_PASSWORD
from ..insights import analyze_change
from ..daily_report import generate_daily_report, get_today_report
from ..ai_analysis import analyze_selection, llm_status
from ..monitor import monitor
from ..models import ChangeInfo, HistoryResponse, RankResponse, SearchResponse, WatchCreate
from ..report import build_compare_rows, to_csv, to_excel, to_markdown, to_pdf

_DESC = """电商选品与竞品监控：榜单、搜索、价格销量历史、涨跌、对比报告、定时告警、UUMit 免费数据。
"""

app = FastAPI(
    title="选品监控面板",
    version="0.2.0",
    description=_DESC,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_last_call: dict = {}


def _throttle(platform: str, sec: float) -> None:
    now = time.time()
    last = _last_call.get(platform, 0.0)
    gap = now - last
    if gap < sec:
        time.sleep(sec - gap)
    _last_call[platform] = time.time()


def _resolve_items(adapter, category, limit):
    _throttle(adapter.platform, adapter.rate_limit_sec)
    return adapter.fetch_rank(category=category, limit=limit)


# 导入即建表（幂等）
cache.init_db()


_PANEL_HTML = (Path(__file__).resolve().parent.parent / "panel.html").read_text(encoding="utf-8")
_BIGSCREEN_HTML = (Path(__file__).resolve().parent.parent / "bigscreen.html").read_text(encoding="utf-8")
_DOCS_HTML = (Path(__file__).resolve().parent.parent / "docs_page.html").read_text(encoding="utf-8")

# ---------------- 访问口令（可选：配置 SHOPMONITOR_PASSWORD 后启用） ----------------
_AUTH_COOKIE = "shopmonitor_auth"


def _auth_token() -> str:
    return hmac.new(SHOPMONITOR_PASSWORD.encode("utf-8"), b"shopmonitor", hashlib.sha256).hexdigest()


def _auth_ok(request: Request) -> bool:
    if not SHOPMONITOR_PASSWORD:
        return True
    tok = request.cookies.get(_AUTH_COOKIE, "")
    return bool(tok) and hmac.compare_digest(tok, _auth_token())


def _serve_page(request: Request, html: str) -> HTMLResponse:
    """页面守卫：未配置口令直接放行；配置了口令则未登录时返回登录页。"""
    if not SHOPMONITOR_PASSWORD:
        return HTMLResponse(html)
    if not _auth_ok(request):
        return HTMLResponse(_LOGIN_HTML)
    if "SM_AUTH" not in html:
        html = html.replace("</head>", "<script>window.SM_AUTH=1;</script></head>")
    return HTMLResponse(html)


_LOGIN_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="/logo.png"><title>访问验证 · ShopMonitor</title><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei",system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#0e2a4d,#1b5bbf 70%,#2f7fe0)}
.box{background:#fff;border-radius:16px;padding:36px 40px;width:340px;box-shadow:0 12px 40px rgba(0,0,0,.3);text-align:center}
.box .logo{font-size:42px}
.box h1{font-size:20px;margin:12px 0 6px;color:#123c6e}
.box p{color:#8a94a3;font-size:13px;margin-bottom:18px}
.box input{width:100%;padding:11px 12px;border:1px solid #d7dce3;border-radius:8px;font-size:14px;margin-bottom:12px;outline:none}
.box input:focus{border-color:#1b5bbf}
.box button{width:100%;padding:11px;border:none;border-radius:8px;background:linear-gradient(135deg,#123c6e,#1b5bbf);color:#fff;font-size:14px;cursor:pointer}
.box button:hover{opacity:.92}
#msg{color:#c05621;font-size:13px;margin-top:10px;min-height:18px}
</style></head><body><div class="box"><div class="logo">🛒</div><h1>ShopMonitor 选品监控</h1><p>已启用访问口令，请输入口令进入</p><input id="pwd" type="password" placeholder="访问口令" autofocus><button onclick="go()">进入</button><div id="msg"></div></div><script>
async function go(){const p=document.getElementById('pwd').value;if(!p){document.getElementById('msg').textContent='请输入口令';return;}
const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p})});
const d=await r.json();
if(r.ok){location.href=location.pathname;}else{document.getElementById('msg').textContent=d.message||'口令错误';}}
document.getElementById('pwd').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
</script></body></html>"""


@app.post("/login", include_in_schema=False)
def login(body: dict = {}) -> JSONResponse:
    if not SHOPMONITOR_PASSWORD:
        return JSONResponse({"ok": True, "message": "未启用口令"})
    pwd = str(body.get("password") or "")
    if hmac.compare_digest(pwd, SHOPMONITOR_PASSWORD):
        resp = JSONResponse({"ok": True, "message": "ok"})
        resp.set_cookie(_AUTH_COOKIE, _auth_token(), httponly=True, max_age=60 * 60 * 24 * 7, samesite="lax")
        return resp
    return JSONResponse({"ok": False, "message": "口令错误"}, status_code=401)


@app.post("/logout", include_in_schema=False)
def logout() -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_AUTH_COOKIE)
    return resp


@app.get("/", include_in_schema=False)
@app.get("/面板", include_in_schema=False)
def panel(request: Request) -> HTMLResponse:
    """中文看板。"""
    return _serve_page(request, _PANEL_HTML)


@app.get("/logo.png", include_in_schema=False)
def logo_png():
    from fastapi.responses import FileResponse
    p = Path(__file__).resolve().parent.parent.parent / "assets" / "logo.png"
    return FileResponse(p, media_type="image/png") if p.exists() else Response(status_code=404)


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    from fastapi.responses import FileResponse
    p = Path(__file__).resolve().parent.parent.parent / "assets" / "favicon.png"
    return FileResponse(p, media_type="image/x-icon") if p.exists() else Response(status_code=404)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}


@app.get("/大屏", include_in_schema=False)
@app.get("/bigscreen", include_in_schema=False)
def bigscreen(request: Request) -> HTMLResponse:
    """数据大屏：深色全屏看板，自动刷新。"""
    return _serve_page(request, _BIGSCREEN_HTML)


@app.get("/接口文档", include_in_schema=False)
@app.get("/api-docs", include_in_schema=False)
def api_docs_page(request: Request) -> HTMLResponse:
    """自定义中文接口文档：快速开始 + 电商配置引导 + 颗粒化接口目录。"""
    return _serve_page(request, _DOCS_HTML)


# ---------------- 平台 ----------------
@app.get(
    "/api/v1/platforms",
    response_model=dict,
    summary="平台列表（含可用性）",
    tags=["平台"],
)
@app.get(
    "/api/v1/平台列表",
    response_model=dict,
    summary="平台列表（含可用性）",
    tags=["平台"],
)
def platforms() -> dict:
    return {"platforms": list_platforms()}


# ---------------- 榜单 ----------------
@app.get(
    "/api/v1/rank/{platform}",
    response_model=RankResponse,
    summary="拉取榜单/热卖",
    description="拉取指定平台榜单/热卖商品。category 可选；fresh=true 强制刷新；真实采集失败自动降级为演示数据（degraded=true）。",
    tags=["榜单"],
)
@app.get(
    "/api/v1/榜单/{platform}",
    response_model=RankResponse,
    summary="拉取榜单/热卖",
    description="中文路径别名，等价于 /api/v1/rank/{platform}。",
    tags=["榜单"],
)
def rank(
    platform: str,
    category: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    fresh: bool = False,
) -> RankResponse:
    adapter = get_adapter(platform)
    cat = category or adapter.default_category
    cache_key = f"{cat or ''}|{limit}"  # 缓存键含 limit，避免不同条数命中错缓存
    if not fresh:
        cached = cache.get_rank_cache(platform, cache_key, DEFAULT_RANK_TTL)
        if cached:
            return RankResponse(**cached)
    try:
        items = _resolve_items(adapter, category or adapter.default_category, limit)
        source, degraded = "live", False
    except CollectorError as e:
        if ALLOW_MOCK_FALLBACK and adapter.platform != "mock":
            items = MockAdapter(platform=adapter.platform).fetch_rank(
                category=category or adapter.default_category, limit=limit
            )
            source, degraded = "mock", True
        else:
            raise HTTPException(502, detail=f"{adapter.display_name} 采集失败：{e}") from e
    for p in items:
        cache.upsert_product(p)
        cache.save_history(p.platform, p.product_id, p.price, p.sales, p.rating, p.review_count)
    try:
        cache.record_rank_snapshot(platform, cat, items)
    except Exception:  # noqa: BLE001
        pass
    resp = RankResponse(platform=platform, category=cat, source=source, degraded=degraded, items=items)
    cache.set_rank_cache(platform, cache_key, resp.model_dump(mode="json"))
    return resp


# ---------------- 搜索 ----------------
@app.get(
    "/api/v1/search/{platform}",
    response_model=SearchResponse,
    summary="关键词搜索",
    description="按关键词搜索商品，返回搜索位次排名（核心关键词排名监控）。",
    tags=["搜索"],
)
@app.get(
    "/api/v1/搜索/{platform}",
    response_model=SearchResponse,
    summary="关键词搜索",
    description="中文路径别名，等价于 /api/v1/search/{platform}。",
    tags=["搜索"],
)
def search(
    platform: str,
    keyword: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
) -> SearchResponse:
    adapter = get_adapter(platform)
    if not adapter.supports_search:
        raise HTTPException(400, detail=f"{adapter.display_name} 暂不支持关键词搜索")
    try:
        _throttle(adapter.platform, adapter.rate_limit_sec)
        items = adapter.fetch_search(keyword=keyword, limit=limit)
        source, degraded = "live", False
    except CollectorError as e:
        if ALLOW_MOCK_FALLBACK and adapter.platform != "mock":
            items = MockAdapter(platform=adapter.platform).fetch_search(keyword=keyword, limit=limit)
            source, degraded = "mock", True
        else:
            raise HTTPException(502, detail=f"{adapter.display_name} 搜索失败：{e}") from e
    for p in items:
        cache.upsert_product(p)
        cache.save_history(p.platform, p.product_id, p.price, p.sales, p.rating, p.review_count)
    return SearchResponse(platform=platform, keyword=keyword, source=source, degraded=degraded, items=items)


# ---------------- 商品 ----------------
def _with_est(d: dict, platform: str) -> dict:
    """给商品快照附加预估毛利 + 预估月销/月 GMV（成本40%/运费¥8/ACOS10%，可在毛利计算器精算）。"""
    from ..insights import estimate_item_profit, estimate_monthly_sales
    est, margin = estimate_item_profit(d.get("price"), platform, 0.4, 8.0, 0.10)
    d["estimated_profit"] = est
    d["estimated_margin"] = margin
    d["estimated_params"] = {"cost_rate": 0.4, "shipping": 8.0, "acos": 0.10}
    price = d.get("price")
    est_sales = estimate_monthly_sales(platform, d.get("rank"), d.get("sales"))
    d["estimated_monthly_sales"] = est_sales
    d["sales_estimated"] = d.get("sales") is None
    d["estimated_gmv"] = round(float(price) * float(est_sales), 2) if price is not None and est_sales is not None else None
    return d


@app.get(
    "/api/v1/product/{platform}/{product_id}",
    summary="商品详情",
    description="查看商品快照（价格/销量/评分/评论数/库存/促销/店铺等）。",
    tags=["商品"],
)
@app.get(
    "/api/v1/商品/{platform}/{product_id}",
    summary="商品详情",
    description="中文路径别名，等价于 /api/v1/product/{platform}/{product_id}。",
    tags=["商品"],
)
def product(platform: str, product_id: str) -> dict:
    cached = cache.get_product(platform, product_id)
    if cached:
        return _with_est(dict(cached), platform)
    adapter = get_adapter(platform)
    try:
        _throttle(adapter.platform, adapter.rate_limit_sec)
        p = adapter.fetch_product(product_id)
    except CollectorError as e:
        raise HTTPException(502, detail=str(e)) from e
    cache.upsert_product(p)
    cache.save_history(p.platform, p.product_id, p.price, p.sales, p.rating, p.review_count)
    return _with_est(p.model_dump(mode="json"), platform)


@app.get(
    "/api/v1/product/{platform}/{product_id}/history",
    response_model=HistoryResponse,
    summary="价格/销量/评价历史",
    description="按时间倒序返回价格、销量、评分、评论数历史，用于监控降价与趋势。",
    tags=["商品"],
)
@app.get(
    "/api/v1/商品/{platform}/{product_id}/历史",
    response_model=HistoryResponse,
    summary="价格/销量/评价历史",
    description="中文路径别名，等价于 /api/v1/product/{platform}/{product_id}/history。",
    tags=["商品"],
)
def history(platform: str, product_id: str, limit: int = Query(30, ge=1, le=200)) -> HistoryResponse:
    return HistoryResponse(
        platform=platform,
        product_id=product_id,
        records=cache.get_history(platform, product_id, limit),
    )


@app.get(
    "/api/v1/product/{platform}/{product_id}/change",
    response_model=ChangeInfo,
    summary="涨跌分析",
    description="最近两次抓取对比：价格/销量/评价变化、direction（up/down/flat）与一句话结论。",
    tags=["商品"],
)
@app.get(
    "/api/v1/商品/{platform}/{product_id}/涨跌",
    response_model=ChangeInfo,
    summary="涨跌分析",
    description="中文路径别名，等价于 /api/v1/product/{platform}/{product_id}/change。",
    tags=["商品"],
)
def product_change(platform: str, product_id: str) -> ChangeInfo:
    h = cache.get_history(platform, product_id, 2)
    if not h:
        raise HTTPException(404, detail="还没有该商品的历史数据，先抓取一次榜单或商品详情")
    return analyze_change(platform, product_id, h)


# ---------------- 报告 ----------------
@app.get(
    "/api/v1/report/compare",
    summary="选品对比表（md/csv/xlsx）",
    description="按商品 ID 列表生成选品对比表：价格/原价/促销/库存/销量/评分/评论数/店铺/店铺评分/排名/链接 + 预估毛利/毛利率（可传成本占比/运费/ACOS）。fmt=md|csv|xlsx。",
    tags=["报告"],
)
@app.get(
    "/api/v1/报告/对比",
    summary="选品对比表（md/csv/xlsx）",
    description="中文路径别名，等价于 /api/v1/report/compare。",
    tags=["报告"],
)
def compare_report(
    platform: str,
    product_ids: str = Query(..., description="逗号分隔的商品ID列表"),
    fmt: str = Query("md", pattern="^(md|csv|xlsx|json|pdf)$"),
    lang: str = Query("zh", pattern="^(zh|en)$", description="zh=中文 en=English"),
    profit_cost_rate: float = Query(0.4, ge=0, le=1, description="预估采购成本占售价比例（毛利估算用），如 0.4=40%"),
    profit_shipping: float = Query(0.0, ge=0, description="预估运费（元/件，毛利估算用）"),
    profit_acos: float = Query(0.0, ge=0, le=1, description="预估广告费 ACOS（毛利估算用），如 0.1=10%"),
) -> Response:
    ids = [x.strip() for x in product_ids.split(",") if x.strip()]
    if not ids:
        raise HTTPException(400, detail="product_ids 不能为空")
    rows = build_compare_rows(
        platform, ids,
        profit_cost_rate=profit_cost_rate, profit_shipping=profit_shipping, profit_acos=profit_acos,
    )
    if fmt == "pdf":
        import os
        import tempfile

        tmp = os.path.join(tempfile.gettempdir(), f"compare_{int(time.time())}.pdf")
        to_pdf(rows, tmp, lang=lang)
        with open(tmp, "rb") as f:
            content = f.read()
        os.unlink(tmp)
        return Response(content, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=compare.pdf"})
    if fmt == "json":
        return [r.model_dump(mode="json") for r in rows]
    if fmt == "csv":
        return Response(to_csv(rows, lang=lang), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=compare.csv"})
    if fmt == "xlsx":
        import os
        import tempfile

        tmp = os.path.join(tempfile.gettempdir(), f"compare_{int(time.time())}.xlsx")
        to_excel(rows, tmp, lang=lang)
        with open(tmp, "rb") as f:
            content = f.read()
        os.unlink(tmp)
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=compare.xlsx"},
        )
    return Response(to_markdown(rows, lang=lang), media_type="text/markdown; charset=utf-8")


# ---------------- UUMit 免费数据 ----------------
@app.get(
    "/api/v1/uumit/status",
    summary="UUMit 账户状态",
    description="UUMit 钱包余额与 AI 额度汇总（只读，敏感字段已剔除）。",
    tags=["UUMit 免费数据"],
)
@app.get(
    "/api/v1/uumit/状态",
    summary="UUMit 账户状态",
    description="中文路径别名，等价于 /api/v1/uumit/status。",
    tags=["UUMit 免费数据"],
)
def uumit_status() -> dict:
    try:
        acc = uumit_feed.account_status()
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e
    return {"account": acc, "free_credits": uumit_feed.free_credits_summary()}


@app.get(
    "/api/v1/uumit/free-data",
    summary="发现免费数据能力",
    description="按意图 preview 发现 UUMit 免费（price_ut=0）数据能力，不扣费。",
    tags=["UUMit 免费数据"],
)
@app.get(
    "/api/v1/uumit/免费数据",
    summary="发现免费数据能力",
    description="中文路径别名，等价于 /api/v1/uumit/free-data。",
    tags=["UUMit 免费数据"],
)
def uumit_free_data(intent: str = "电商商品销量与价格数据", top: int = Query(10, ge=1, le=30)) -> dict:
    try:
        caps = uumit_feed.discover_free_capabilities(intent=intent, top=top)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e
    return {"intent": intent, "free_count": len(caps), "capabilities": caps}


@app.get(
    "/api/v1/uumit/data/{api_id}/detail",
    summary="数据 API 详情",
    description="查看 UUMit 数据 API 的入参/返回 schema（只读）。",
    tags=["UUMit 免费数据"],
)
@app.get(
    "/api/v1/uumit/数据/{api_id}/详情",
    summary="数据 API 详情",
    description="中文路径别名，等价于 /api/v1/uumit/data/{api_id}/detail。",
    tags=["UUMit 免费数据"],
)
def uumit_data_detail(api_id: str) -> dict:
    try:
        return uumit_feed.data_api_detail(api_id)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.post(
    "/api/v1/uumit/data/{api_id}/call",
    summary="调用免费数据 API",
    description="只调用 price_ut=0 的免费数据 API；付费接口返回 needs_confirmation，绝不静默扣费。",
    tags=["UUMit 免费数据"],
)
@app.post(
    "/api/v1/uumit/数据/{api_id}/调用",
    summary="调用免费数据 API",
    description="中文路径别名，等价于 /api/v1/uumit/data/{api_id}/call。",
    tags=["UUMit 免费数据"],
)
def uumit_data_call(api_id: str, body: dict = {}) -> dict:
    try:
        return uumit_feed.call_free_data_api(api_id, body)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e

# ---------------- UUMit 大盘数据（免费·真实） ----------------
@app.get(
    "/api/v1/uumit/dashboard",
    summary="大盘数据（UUMit 免费）",
    description="一次取回：账户状态 + 跨平台商品表现 + 电商大盘概览 + 月度趋势（全部 price_ut=0，0 扣费）。fresh=true 强制刷新。",
    tags=["UUMit 大盘数据"],
)
@app.get(
    "/api/v1/uumit/大盘",
    summary="大盘数据（UUMit 免费）",
    description="中文路径别名，等价于 /api/v1/uumit/dashboard。",
    tags=["UUMit 大盘数据"],
)
def uumit_dashboard(fresh: bool = False) -> dict:
    try:
        return uumit_data.dashboard(fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get(
    "/api/v1/uumit/platforms",
    summary="跨平台商品表现",
    description="淘宝/京东平台维度：商品数、均价、销量、评分（UUMit 免费数据，真实）。",
    tags=["UUMit 大盘数据"],
)
@app.get(
    "/api/v1/uumit/平台对比",
    summary="跨平台商品表现",
    description="中文路径别名，等价于 /api/v1/uumit/platforms。",
    tags=["UUMit 大盘数据"],
)
def uumit_platform_perf(fresh: bool = False) -> dict:
    try:
        return uumit_data.platform_performance(fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get(
    "/api/v1/uumit/overview",
    summary="电商大盘经营概览",
    description="订单、用户、商品、成交额、客单价等大盘指标（UUMit 免费数据，真实）。",
    tags=["UUMit 大盘数据"],
)
@app.get(
    "/api/v1/uumit/经营概览",
    summary="电商大盘经营概览",
    description="中文路径别名，等价于 /api/v1/uumit/overview。",
    tags=["UUMit 大盘数据"],
)
def uumit_overview(fresh: bool = False) -> dict:
    try:
        return uumit_data.market_overview(fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get(
    "/api/v1/uumit/trend",
    summary="销售额销量时间趋势",
    description="按月返回成交额、订单、销量、客单价，含环比与残月标注；日期范围 dateFrom/dateTo 真实生效，按季/按年为本地聚合（UUMit 免费数据，真实，0 扣费）。",
    tags=["UUMit 大盘数据"],
)
@app.get(
    "/api/v1/uumit/趋势",
    summary="销售额销量时间趋势",
    description="中文路径别名，等价于 /api/v1/uumit/trend。",
    tags=["UUMit 大盘数据"],
)
def uumit_trend(
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    grain: str = Query("month", pattern="^(day|month|quarter|year)$"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    fresh: bool = False,
) -> dict:
    try:
        return uumit_data.sales_trend(
            keyword=keyword, category=category, brand=brand,
            grain=grain, date_from=date_from, date_to=date_to, fresh=fresh,
        )
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get(
    "/api/v1/uumit/report",
    summary="导出大盘报告",
    description="大盘数据导出：fmt=md 返回 Markdown（可直接贴文档/上架文案），fmt=csv 返回 CSV（可导入 Excel）。",
    tags=["UUMit 大盘数据"],
)
@app.get(
    "/api/v1/uumit/报告",
    summary="导出大盘报告",
    description="中文路径别名，等价于 /api/v1/uumit/report。",
    tags=["UUMit 大盘数据"],
)
def uumit_report(fmt: str = Query("md", pattern="^(md|csv)$"), lang: str = Query("zh", pattern="^(zh|en)$"), fresh: bool = False) -> Response:
    try:
        text = uumit_data.dashboard_report(fmt=fmt, lang=lang, fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e
    if fmt == "csv":
        return Response(text, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="uumit_dashboard.csv"'})
    return Response(text, media_type="text/markdown; charset=utf-8")


@app.get(
    "/api/v1/uumit/suggest",
    summary="淘宝联想词",
    description="输入商品关键词返回淘宝下拉联想词（选词工具），真实免费数据，0 扣费。",
    tags=["UUMit 热搜选词"],
)
@app.get(
    "/api/v1/uumit/联想词",
    summary="淘宝联想词",
    description="中文路径别名，等价于 /api/v1/uumit/suggest。",
    tags=["UUMit 热搜选词"],
)
def uumit_suggest(keyword: str, fresh: bool = False) -> dict:
    try:
        return uumit_data.taobao_suggest(keyword=keyword, fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get(
    "/api/v1/uumit/hot",
    summary="抖音实时热搜",
    description="抖音实时热搜前 10：标题 + 热度 + 视频链接，真实免费数据，0 扣费。",
    tags=["UUMit 热搜选词"],
)
@app.get(
    "/api/v1/uumit/热搜",
    summary="抖音实时热搜",
    description="中文路径别名，等价于 /api/v1/uumit/hot。",
    tags=["UUMit 热搜选词"],
)
def uumit_hot(fresh: bool = False) -> dict:
    try:
        return uumit_data.douyin_hot(fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get(
    "/api/v1/uumit/baidu-hot",
    summary="百度热搜",
    description="百度热搜：type=realtime/novel/movie/teleplay/car/game（实时/小说/电影/电视剧/汽车/游戏），真实免费数据，0 扣费。",
    tags=["UUMit 热搜选词"],
)
@app.get(
    "/api/v1/uumit/百度热搜",
    summary="百度热搜",
    description="中文路径别名，等价于 /api/v1/uumit/baidu-hot。",
    tags=["UUMit 热搜选词"],
)
def uumit_baidu_hot(type: str = "realtime", fresh: bool = False) -> dict:
    try:
        return uumit_data.baidu_hot(type_=type, fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e


@app.get(
    "/api/v1/uumit/hot-report",
    summary="导出热搜选词报告",
    description="抖音热搜 + 百度热搜 + 淘宝联想词 导出：fmt=md 返回 Markdown，fmt=csv 返回 CSV（含 UTF-8 BOM）。",
    tags=["UUMit 热搜选词"],
)
@app.get(
    "/api/v1/uumit/热搜报告",
    summary="导出热搜选词报告",
    description="中文路径别名，等价于 /api/v1/uumit/hot-report。",
    tags=["UUMit 热搜选词"],
)
def uumit_hot_report(fmt: str = Query("md", pattern="^(md|csv)$"), keyword: str = "手机", lang: str = Query("zh", pattern="^(zh|en)$"), fresh: bool = False) -> Response:
    try:
        text = uumit_data.hot_words_report(fmt=fmt, keyword=keyword, lang=lang, fresh=fresh)
    except uumit_feed.UumitError as e:
        raise HTTPException(502, detail=str(e)) from e
    if fmt == "csv":
        return Response(text, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="uumit_hot_words.csv"'})
    return Response(text, media_type="text/markdown; charset=utf-8")


# ---------------- 定时监控（P0） ----------------
@app.get(
    "/api/v1/monitor/status",
    summary="监控状态",
    description="调度线程是否在跑、轮询间隔、关注数、未读告警数。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/状态",
    summary="监控状态",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_status() -> dict:
    return monitor.status()


@app.get(
    "/api/v1/monitor/watches",
    summary="关注列表",
    description="查看所有监控关注项。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/关注列表",
    summary="关注列表",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_watches() -> dict:
    return {"watches": cache.list_watches()}


@app.post(
    "/api/v1/monitor/watches",
    summary="新增关注",
    description="新增监控关注项：mode=keyword 盯榜单/搜索前 N 名；mode=product 盯单个商品。",
    tags=["监控"],
)
@app.post(
    "/api/v1/监控/关注",
    summary="新增关注",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_add_watch(body: WatchCreate) -> dict:
    from ..config import PLAN_LIMITS
    if len(cache.list_watches()) >= PLAN_LIMITS["max_watches"]:
        raise HTTPException(
            403,
            detail=f"当前套餐最多监控 {PLAN_LIMITS['max_watches']} 个关注项（免费版）。升级 Pro 可到 {PLAN_LIMITS['max_watches'] if False else 50}，或调整 配置文件.env 的 SHOPMONITOR_PLAN=pro/enterprise。",
        )
    wid = cache.add_watch(
        platform=body.platform,
        mode=body.mode,
        keyword=body.keyword,
        category=body.category,
        product_id=body.product_id,
        alias=body.alias,
        top_n=body.top_n,
        target_price=body.target_price,
        enabled=body.enabled,
    )
    return {"id": wid, "watch": cache.get_watch(wid)}


@app.delete(
    "/api/v1/monitor/watches/{watch_id}",
    summary="删除关注",
    description="删除监控关注项及其状态。",
    tags=["监控"],
)
@app.delete(
    "/api/v1/监控/关注/{watch_id}",
    summary="删除关注",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_delete_watch(watch_id: int) -> dict:
    ok = cache.delete_watch(watch_id)
    if not ok:
        raise HTTPException(404, detail=f"关注项 {watch_id} 不存在")
    return {"deleted": True, "id": watch_id}


@app.post(
    "/api/v1/monitor/watches/{watch_id}/toggle",
    summary="启停关注",
    description="开关某个监控关注项。",
    tags=["监控"],
)
@app.post(
    "/api/v1/监控/关注/{watch_id}/开关",
    summary="启停关注",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_toggle_watch(watch_id: int) -> dict:
    w = cache.toggle_watch(watch_id)
    if not w:
        raise HTTPException(404, detail=f"关注项 {watch_id} 不存在")
    return {"watch": w}


@app.post(
    "/api/v1/monitor/run",
    summary="立即巡检一轮",
    description="手动触发一轮监控采集与告警判断（不用等调度周期）。",
    tags=["监控"],
)
@app.post(
    "/api/v1/监控/运行",
    summary="立即巡检一轮",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_run_once() -> dict:
    return monitor.run_once()


@app.get(
    "/api/v1/monitor/alerts",
    summary="告警列表",
    description="查询告警记录，unread=true 只看未读。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/告警",
    summary="告警列表",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_alerts(limit: int = Query(50, ge=1, le=500), unread: bool = False) -> dict:
    return {
        "total": len(cache.list_alerts(limit=limit * 10, unread_only=False)),
        "unread": cache.unread_alert_count(),
        "alerts": cache.list_alerts(limit=limit, unread_only=unread),
    }


@app.post(
    "/api/v1/monitor/alerts/read",
    summary="标记已读",
    description="body: {ids: [1,2,3]} 或 {} 表示全部标记已读。",
    tags=["监控"],
)
@app.post(
    "/api/v1/监控/告警/已读",
    summary="标记已读",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_alerts_read(body: dict = {}) -> dict:
    ids = body.get("ids") if isinstance(body, dict) else None
    n = cache.mark_alerts_read(ids)
    return {"marked": n}


# ---------------- 日报 + 排名趋势 ----------------
@app.post(
    "/api/v1/monitor/daily-report",
    summary="生成日报",
    description="立即生成今日日报：大盘 + 热搜 + 今日告警 + 监控概况，落盘并推送 Webhook。",
    tags=["监控"],
)
@app.post(
    "/api/v1/监控/日报",
    summary="生成日报",
    description="中文路径别名，等价于 /api/v1/monitor/daily-report。",
    tags=["监控"],
)
def monitor_daily_report_generate(push: bool = True) -> dict:
    try:
        return generate_daily_report(push=push)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)) from e


@app.get(
    "/api/v1/monitor/daily-report",
    summary="查看今日日报",
    description="返回今日日报 Markdown（未生成返回 404）。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/日报",
    summary="查看今日日报",
    description="中文路径别名，等价于 GET /api/v1/monitor/daily-report。",
    tags=["监控"],
)
def monitor_daily_report_view(fmt: str = Query("md", pattern="^(md|pdf)$")) -> Response:
    md = get_today_report()
    if md is None:
        raise HTTPException(404, detail="今日日报尚未生成，请先 POST /api/v1/监控/日报")
    if fmt == "pdf":
        import os
        import tempfile
        from ..report import md_to_pdf
        tmp = os.path.join(tempfile.gettempdir(), f"daily_{int(time.time())}.pdf")
        md_to_pdf(md, tmp, title="电商监控日报")
        with open(tmp, "rb") as f:
            content = f.read()
        os.unlink(tmp)
        return Response(content, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=daily_report.pdf"})
    return Response(md, media_type="text/markdown; charset=utf-8")


@app.get(
    "/api/v1/monitor/rank-trend",
    summary="排名趋势",
    description="某关注项的排名/价格/销量历史序列（按时间升序），用于画趋势图。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/排名趋势",
    summary="排名趋势",
    description="中文路径别名，等价于 /api/v1/monitor/rank-trend。",
    tags=["监控"],
)
def monitor_rank_trend(watch_id: int, limit: int = Query(300, ge=1, le=1000)) -> dict:
    from .. import cache as _cache
    w = _cache.get_watch(watch_id)
    if not w:
        raise HTTPException(404, detail=f"关注项 {watch_id} 不存在")
    return {
        "watch": w,
        "products": _cache.list_monitor_products(watch_id),
        "records": _cache.get_monitor_history(watch_id, limit=limit),
    }


# ---------------- AI 选品分析 ----------------
@app.post(
    "/api/v1/ai/analyze",
    summary="AI 选品分析",
    description="基于大盘 + 热搜 + 联想词 + 趋势，调用已配置的大模型（OpenAI 兼容）生成选品分析。未配置 key 返回 needs_key。",
    tags=["AI 选品分析"],
)
@app.post(
    "/api/v1/ai/选品分析",
    summary="AI 选品分析",
    description="中文路径别名，等价于 /api/v1/ai/analyze。",
    tags=["AI 选品分析"],
)
def ai_analyze(keyword: str = "", fresh: bool = False) -> dict:
    try:
        return analyze_selection(keyword=keyword, fresh=fresh)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)) from e


@app.get(
    "/api/v1/ai/status",
    summary="AI 配置状态",
    description="查看大模型是否已配置（不返回 Key 本身）。",
    tags=["AI 选品分析"],
)
@app.get(
    "/api/v1/ai/状态",
    summary="AI 配置状态",
    description="中文路径别名，等价于 /api/v1/ai/status。",
    tags=["AI 选品分析"],
)
def ai_status() -> dict:
    return llm_status()


# ---------------- 选品工具：毛利估算 + 今日变动榜 ----------------
@app.get(
    "/api/v1/tools/profit",
    summary="毛利估算器",
    description="输入售价/采购成本/运费/平台佣金率/其他费率/税率/件数，按 毛利=售价×件数−（成本+运费+佣金+其他+税）×件数 估算毛利、毛利率与 ROI（选品定价用）。税率如国内增值税 13% 填 0.13；跨境站点多填 0。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/毛利估算",
    summary="毛利估算器",
    description="中文路径别名，等价于 /api/v1/tools/profit。",
    tags=["选品工具"],
)
def tools_profit(
    sale_price: float = Query(..., gt=0, description="售价（按结算币种）"),
    cost: float = Query(..., gt=0, description="采购成本（人民币）"),
    shipping: float = Query(0, ge=0, description="运费/物流（人民币/件）"),
    commission_rate: float = Query(0.05, ge=0, le=0.6, description="平台佣金率，如 0.05=5%"),
    other_rate: float = Query(0.01, ge=0, le=0.3, description="其他费率(包装/手续费等)"),
    tax_rate: float = Query(0.0, ge=0, le=0.5, description="税率，如 0.13=13%"),
    quantity: int = Query(1, ge=1, le=100000, description="件数"),
    currency: str = Query("CNY", description="结算币种，如 CNY/USD/EUR/GBP/MYR/THB…"),
    fx_rate: Optional[float] = Query(None, ge=0, description="汇率：1 外币=多少人民币；留空自动取实时汇率"),
    fulfillment: str = Query("手动", description="运营/发货模式标签，如 Amazon FBA / FBM（预设见 /api/v1/tools/fulfillment）"),
    fulfillment_fee: float = Query(0.0, ge=0, description="单位履约费（结算币种/件，如 Amazon FBA 履行费）"),
    storage_fee: float = Query(0.0, ge=0, description="单位月仓储费（结算币种/件·月，海外仓/平台仓）"),
    payment_fee_rate: float = Query(0.0, ge=0, le=0.1, description="收款/结汇手续费率，如 0.005=0.5%"),
    fx_loss_rate: float = Query(0.0, ge=0, le=0.1, description="汇损率，如 0.005=0.5%"),
    packaging_fee: float = Query(0.0, ge=0, description="打包/耗材费（人民币/件）"),
    acos_rate: float = Query(0.0, ge=0, le=1.0, description="广告费 ACOS：广告支出占销售额比例，如 0.15=15%"),
    long_storage_fee: float = Query(0.0, ge=0, description="长期仓储费（结算币种/件·月，如 Amazon 超龄库存费）"),
    removal_fee: float = Query(0.0, ge=0, description="移除/弃置费（结算币种/件，一次性）"),
    duty_rate: float = Query(0.0, ge=0, le=0.5, description="进口关税率（占采购成本比例），如 0.08=8%"),
    return_rate: float = Query(0.0, ge=0, le=0.5, description="退货/退款率（按全损简化），如 0.05=5%"),
    fixed_fee: float = Query(0.0, ge=0, description="一次性固定费（结算币种，如平台月租/保证金分摊）"),
) -> dict:
    from ..insights import estimate_profit
    return estimate_profit(
        sale_price=sale_price, cost=cost, shipping=shipping,
        commission_rate=commission_rate, other_rate=other_rate,
        tax_rate=tax_rate, quantity=quantity,
        currency=currency, fx_rate=fx_rate,
        fulfillment=fulfillment, fulfillment_fee=fulfillment_fee,
        storage_fee=storage_fee, payment_fee_rate=payment_fee_rate,
        fx_loss_rate=fx_loss_rate, packaging_fee=packaging_fee,
        acos_rate=acos_rate, long_storage_fee=long_storage_fee,
        removal_fee=removal_fee, duty_rate=duty_rate,
        return_rate=return_rate, fixed_fee=fixed_fee,
    )


@app.get(
    "/api/v1/tools/rates",
    summary="跨境结算币种与汇率",
    description="返回各平台常用结算币种、货币信息与人民币汇率（1 外币=多少人民币）。实时获取，失败用内置快照兜底。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/汇率",
    summary="跨境结算币种与汇率",
    description="中文路径别名，等价于 /api/v1/tools/rates。",
    tags=["选品工具"],
)
def tools_rates() -> dict:
    from ..currencies import CURRENCIES, PLATFORM_CURRENCIES, get_rates
    d = get_rates()
    return {
        "base": "CNY",
        "rates": d["rates"],
        "source": d["source"],
        "updated": d["updated"],
        "currencies": CURRENCIES,
        "platforms": PLATFORM_CURRENCIES,
    }


@app.get(
    "/api/v1/tools/fulfillment",
    summary="各平台运营/发货模式预设",
    description="返回各平台运营/发货模式（Amazon FBA/FBM、平台物流/自发货/海外仓、一件代发等）的费用预设，供毛利计算器一键套用。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/运营模式",
    summary="各平台运营/发货模式预设",
    description="中文路径别名，等价于 /api/v1/tools/fulfillment。",
    tags=["选品工具"],
)
def tools_fulfillment(platform: Optional[str] = Query(None, description="平台 key，如 amazon_open；留空返回全部")) -> dict:
    from ..fulfillment import (
        CATEGORY_PRESETS,
        FBA_FULFILLMENT_TIERS,
        FULL_TEMPLATES,
        get_category_presets,
        get_fulfillment_modes,
    )
    modes = get_fulfillment_modes(platform)
    return {
        "count": len(modes),
        "items": modes,
        "fba_tiers": FBA_FULFILLMENT_TIERS,
        "category_presets": get_category_presets(),
        "templates": FULL_TEMPLATES,
    }


@app.get(
    "/api/v1/tools/profit-overview",
    summary="预估毛利概览",
    description="基于关注商品快照（无则用演示榜）计算预估毛利统计：总毛利/平均毛利/盈利占比 + Top 商品列表（大屏卡片用）。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/毛利概览",
    summary="预估毛利概览",
    description="中文路径别名，等价于 /api/v1/tools/profit-overview。",
    tags=["选品工具"],
)
def tools_profit_overview(
    limit: int = Query(10, ge=1, le=50),
    profit_cost_rate: float = Query(0.4, ge=0, le=1, description="预估成本占售价比例"),
    profit_shipping: float = Query(8.0, ge=0, description="预估运费（元/件）"),
    profit_acos: float = Query(0.10, ge=0, le=1, description="预估广告费 ACOS"),
    profit_duty_rate: float = Query(0.0, ge=0, le=0.5, description="预估进口关税率"),
    profit_return_rate: float = Query(0.03, ge=0, le=0.5, description="预估退货率"),
) -> dict:
    from .. import cache as _cache
    from ..insights import estimate_item_profit
    items = []
    try:
        items = _cache.watch_overview()
    except Exception:  # noqa: BLE001
        items = []
    source = "监控快照"
    if not items:
        from ..collectors.mock import MockAdapter
        prods = MockAdapter().fetch_rank(category="数码", limit=20)
        items = [{"platform": "mock", "title": p.title, "product_id": p.product_id,
                  "price": p.price, "sales": p.sales, "rank": p.rank} for p in prods]
        source = "演示榜单"
    enriched = []
    for x in items:
        est, margin = estimate_item_profit(
            x.get("price"), x.get("platform"), profit_cost_rate, profit_shipping,
            profit_acos, profit_duty_rate, profit_return_rate)
        enriched.append({
            "platform": x.get("platform"), "product_id": x.get("product_id"),
            "title": x.get("title") or x.get("product_id") or "-",
            "price": x.get("price"), "sales": x.get("sales"), "rank": x.get("rank"),
            "estimated_profit": est, "estimated_margin": margin,
        })
    with_profit = [e for e in enriched if e.get("estimated_profit") is not None]
    total = sum(e["estimated_profit"] for e in with_profit)
    avg = total / len(with_profit) if with_profit else 0.0
    positive = sum(1 for e in with_profit if e["estimated_profit"] >= 0)
    top = sorted(with_profit, key=lambda e: -(e["estimated_profit"] or 0))[:limit]
    return {
        "source": source,
        "count": len(with_profit),
        "total_profit": round(total, 2),
        "avg_profit": round(avg, 2),
        "positive_count": positive,
        "positive_ratio": round(positive / len(with_profit) * 100, 1) if with_profit else 0.0,
        "params": {
            "cost_rate": profit_cost_rate, "shipping": profit_shipping, "acos": profit_acos,
            "duty_rate": profit_duty_rate, "return_rate": profit_return_rate,
        },
        "items": top,
    }


@app.get(
    "/api/v1/picks",
    summary="选品库列表",
    description="选品库（收藏/备选管理）：考察中/可上架/已上架/放弃，含备注与来源关键词。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/选品库",
    summary="选品库列表",
    description="中文路径别名，等价于 /api/v1/picks。",
    tags=["选品工具"],
)
def picks_list(status: Optional[str] = Query(None, description="按状态筛选：考察中/可上架/已上架/放弃")) -> dict:
    from .. import cache as _cache
    items = _cache.list_picks(status=status)
    return {"count": len(items), "items": items}


@app.post(
    "/api/v1/picks",
    summary="加入选品库",
    description="把商品加入选品库（同平台+商品已存在则更新）。",
    tags=["选品工具"],
)
@app.post(
    "/api/v1/选品库",
    summary="加入选品库",
    description="中文路径别名，等价于 POST /api/v1/picks。",
    tags=["选品工具"],
)
def picks_add(body: dict = {}) -> dict:
    from .. import cache as _cache
    platform = str(body.get("platform") or "").strip()
    product_id = str(body.get("product_id") or "").strip()
    if not platform or not product_id:
        raise HTTPException(400, detail="platform / product_id 必填")
    pid = _cache.add_pick(
        platform, product_id,
        title=str(body.get("title") or ""),
        price=body.get("price"),
        status=str(body.get("status") or "考察中"),
        note=str(body.get("note") or ""),
        keyword=str(body.get("keyword") or ""),
    )
    return {"id": pid, "message": "已加入选品库"}


@app.patch(
    "/api/v1/picks/{pick_id}",
    summary="更新选品库条目",
    description="更新状态（考察中/可上架/已上架/放弃）或备注。",
    tags=["选品工具"],
)
@app.patch(
    "/api/v1/选品库/{pick_id}",
    summary="更新选品库条目",
    description="中文路径别名。",
    tags=["选品工具"],
)
def picks_update(pick_id: int, body: dict = {}) -> dict:
    from .. import cache as _cache
    ok = _cache.update_pick(pick_id, status=body.get("status"), note=body.get("note"))
    if not ok:
        raise HTTPException(404, detail="选品不存在")
    return {"ok": True, "id": pick_id}


@app.delete(
    "/api/v1/picks/{pick_id}",
    summary="删除选品库条目",
    tags=["选品工具"],
)
@app.delete(
    "/api/v1/选品库/{pick_id}",
    summary="删除选品库条目",
    description="中文路径别名。",
    tags=["选品工具"],
)
def picks_delete(pick_id: int) -> dict:
    from .. import cache as _cache
    ok = _cache.delete_pick(pick_id)
    if not ok:
        raise HTTPException(404, detail="选品不存在")
    return {"ok": True, "id": pick_id}


@app.get(
    "/api/v1/tools/blue-ocean",
    summary="蓝海选词",
    description="结合抖音热搜热度 + 淘宝联想词竞争度，给热搜词算「蓝海指数」：热度高、联想词少 = 蓝海机会。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/蓝海选词",
    summary="蓝海选词",
    description="中文路径别名，等价于 /api/v1/tools/blue-ocean。",
    tags=["选品工具"],
)
def tools_blue_ocean(limit: int = Query(8, ge=1, le=20)) -> dict:
    from .. import uumit_data as ud
    try:
        hot = ud.douyin_hot()
        words = (hot.get("items") or [])[:limit]
    except Exception:  # noqa: BLE001
        return {"source": "UUMit", "count": 0, "items": [],
                "note": "热搜数据暂不可用（UUMit 未连接），可稍后再试"}
    items = []
    for it in words:
        word = (it.get("title") or "").strip()
        if not word:
            continue
        heat = int(it.get("hot") or 0)
        related = -1
        try:
            sg = ud.taobao_suggest(word)
            related = int(sg.get("count") or len(sg.get("items") or []))
        except Exception:  # noqa: BLE001
            related = -1
        items.append({"rank": it.get("rank"), "word": word, "heat": heat, "related_count": related})
    max_hot = max((x["heat"] for x in items), default=1) or 1
    for x in items:
        rel = max(x["related_count"], 0)
        x["score"] = round((x["heat"] / max_hot) * 100 / (1 + rel) * 10, 1)
        if x["related_count"] < 0:
            x["suggest"] = "联想词未知，仅看热度"
        elif rel <= 3:
            x["suggest"] = "热度高·联想词少 → 蓝海机会"
        elif rel <= 8:
            x["suggest"] = "竞争中等，可切入"
        else:
            x["suggest"] = "联想词多·竞争激烈，慎入"
    items.sort(key=lambda x: -x["score"])
    for i, x in enumerate(items, start=1):
        x["rank"] = i
    return {
        "source": "UUMit 免费（热搜+联想词）",
        "count": len(items),
        "note": "蓝海指数 = 热度归一化 ÷ (1 + 淘宝联想词数)，指数越高越蓝海",
        "items": items,
    }


@app.get(
    "/api/v1/tools/shop-monitor",
    summary="竞品店铺监控",
    description="输入店铺 ID，拉取该店铺在售商品（Shopee 开放平台；TikTok Shop 用商家授权）。凭证未配置时返回引导提示。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/店铺监控",
    summary="竞品店铺监控",
    description="中文路径别名，等价于 /api/v1/tools/shop-monitor。",
    tags=["选品工具"],
)
def tools_shop_monitor(
    platform: str = Query("shopee_open", description="shopee_open / tiktok_shop"),
    shop_id: str = Query("", description="店铺 ID（Shopee）；TikTok 用配置里的商家授权"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    from ..collectors.base import CollectorError
    from ..collectors.registry import get_adapter
    a = get_adapter(platform)
    if platform == "shopee_open":
        if not a.is_configured():
            return {"ok": False, "platform": platform, "count": 0, "items": [],
                    "message": "需配置 Shopee 开放平台凭证（PartnerID/PartnerKey/授权Token）后使用：接口文档 → 配置中心 → 官方开放平台凭证（跨境）。"}
        if shop_id:
            a.shop_id_override = str(shop_id).strip()
    elif platform == "tiktok_shop":
        if not a.is_configured():
            return {"ok": False, "platform": platform, "count": 0, "items": [],
                    "message": "需配置 TikTok Shop AppKey/Secret + 商家授权 Token 后使用：接口文档 → 配置中心 → 官方开放平台凭证（跨境）。"}
    else:
        return {"ok": False, "platform": platform, "count": 0, "items": [],
                "message": f"店铺监控暂只支持 Shopee / TikTok Shop（当前：{platform}）"}
    try:
        items = a.fetch_rank(limit=limit)
        return {"ok": True, "platform": platform, "shop_id": shop_id, "count": len(items),
                "items": [i.model_dump(mode="json") for i in items], "source": "live"}
    except CollectorError as e:
        return {"ok": False, "platform": platform, "shop_id": shop_id, "count": 0, "items": [],
                "message": str(e)}


@app.get(
    "/api/v1/tools/source",
    summary="1688 一键找货源",
    description="拿商品词去 1688 搜同款货源（价格/厂家），选品比价用。需 1688 开放平台凭证。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/找货源",
    summary="1688 一键找货源",
    description="中文路径别名，等价于 /api/v1/tools/source。",
    tags=["选品工具"],
)
def tools_source(keyword: str = Query(..., description="商品词/标题"), limit: int = Query(20, ge=1, le=50)) -> dict:
    from ..collectors.base import CollectorError
    from ..collectors.registry import get_adapter
    a = get_adapter("alibaba_open")
    if not a.is_configured():
        return {"ok": False, "platform": "alibaba_open", "count": 0, "items": [],
                "message": "需配置 1688 开放平台凭证（AppKey/Secret + 授权 Token）后使用：接口文档 → 配置中心 → 官方开放平台凭证。"}
    try:
        items = a.fetch_search(keyword, limit=limit)
        return {"ok": True, "platform": "alibaba_open", "keyword": keyword, "count": len(items),
                "items": [i.model_dump(mode="json") for i in items], "source": "live"}
    except CollectorError as e:
        return {"ok": False, "platform": "alibaba_open", "keyword": keyword, "count": 0, "items": [],
                "message": str(e)}


@app.get(
    "/api/v1/tools/rank-trend",
    summary="类目榜单历史趋势",
    description="近 N 天类目榜单快照：每日商品数/均价/新品数（需每天拉一次该榜单自动积累）。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/榜单趋势",
    summary="类目榜单历史趋势",
    description="中文路径别名，等价于 /api/v1/tools/rank-trend。",
    tags=["选品工具"],
)
def tools_rank_trend(
    platform: str = Query("mock", description="平台 key"),
    category: str = Query("数码", description="类目/关键词"),
    days: int = Query(7, ge=2, le=30),
) -> dict:
    from .. import cache as _cache
    return _cache.rank_snapshot_trend(platform, category, days)


@app.get(
    "/api/v1/tools/price-bands",
    summary="价格带分析",
    description="拉取类目榜单，按价格带分布统计商品数/平均销量/评分，给出建议定价带（选品经典功能）。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/价格带分析",
    summary="价格带分析",
    description="中文路径别名，等价于 /api/v1/tools/price-bands。",
    tags=["选品工具"],
)
def _price_bands_for(platform: str, category: str, limit: int = 100) -> dict:
    """单个平台的价格带分析（供单平台/跨平台对比复用）。"""
    adapter = get_adapter(platform)
    cat = category or adapter.default_category
    try:
        items = _resolve_items(adapter, cat, limit)
        source = "live"
    except CollectorError:
        items = MockAdapter(platform=platform).fetch_rank(category=cat, limit=limit)
        source = "mock"
    bands = [(0, 50, "0-50"), (50, 100, "50-100"), (100, 200, "100-200"),
             (200, 500, "200-500"), (500, 1000, "500-1000"), (1000, None, "1000+")]
    rows = []
    priced = [p for p in items if p.price is not None]
    for lo, hi, label in bands:
        in_band = [p for p in priced if p.price >= lo and (hi is None or p.price < hi)]
        sales = sum(p.sales or 0 for p in in_band)
        rows.append({
            "band": label, "lo": lo, "hi": hi,
            "count": len(in_band),
            "avg_sales": round(sales / len(in_band)) if in_band else 0,
            "avg_rating": round(sum(p.rating or 0 for p in in_band) / len(in_band), 2) if in_band else None,
            "sales_total": sales,
        })
    total = len(priced)
    avg_price = round(sum(p.price for p in priced) / total, 2) if total else None
    rows.sort(key=lambda x: -x["count"])
    suggestion = None
    for r in rows:
        if r["count"] >= max(3, int(total * 0.05)) and r["avg_sales"] > 0:
            suggestion = r["band"]
            break
    return {"platform": platform, "category": cat, "source": source,
            "total": total, "avg_price": avg_price, "bands": rows, "suggestion": suggestion}


def tools_price_bands(
    platform: str = Query("mock", description="平台 key"),
    category: str = Query("数码", description="类目/关键词"),
    limit: int = Query(100, ge=20, le=200),
) -> dict:
    return _price_bands_for(platform, category, limit)


@app.get(
    "/api/v1/tools/price-bands-compare",
    summary="跨平台价格带对比",
    description="同一关键词在多个平台的价格带分布对比，标出哪边好卖（建议定价带/均价/平均销量）。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/跨平台价格带",
    summary="跨平台价格带对比",
    description="中文路径别名，等价于 /api/v1/tools/price-bands-compare。",
    tags=["选品工具"],
)
def tools_price_bands_compare(
    category: str = Query("数码", description="类目/关键词"),
    platforms: str = Query("jd,taobao,pdd,shopee,amazon,aliexpress,mock", description="逗号分隔的平台 key"),
    limit: int = Query(60, ge=20, le=100),
) -> dict:
    plats = [x.strip() for x in platforms.split(",") if x.strip()]
    results = []
    for pf in plats:
        try:
            r = _price_bands_for(pf, category, limit)
            results.append({
                "platform": pf,
                "name": get_adapter(pf).display_name,
                "source": r["source"],
                "total": r["total"],
                "avg_price": r.get("avg_price"),
                "suggestion": r["suggestion"],
                "top_band": r["bands"][0]["band"] if r["bands"] else None,
            })
        except Exception as e:  # noqa: BLE001
            results.append({"platform": pf, "name": pf, "error": str(e)})
    results.sort(key=lambda x: -x.get("total", 0))
    return {"category": category, "count": len(results), "items": results}


@app.post(
    "/api/v1/settings/fill-datapack",
    summary="一键填数据包",
    description="给一个 GitHub Pages 数据包 base 地址，自动把 7 平台数据源 URL 填好（{base}/data/xxx.json）。",
    tags=["设置"],
)
@app.post(
    "/api/v1/配置/填数据包",
    summary="一键填数据包",
    description="中文路径别名。",
    tags=["设置"],
)
def settings_fill_datapack(body: dict = {}, restart: bool = True) -> dict:
    from ..config import BASE_DIR, rewrite_env_file
    from ..preset_data import FILE_MAP
    base = str(body.get("base_url") or "").rstrip("/")
    if not base:
        return {"ok": False, "message": "请填写数据包 base 地址（如 https://user.github.io/repo）"}
    updates = {}
    for fname in FILE_MAP.values():
        env = f"SHOPMONITOR_{fname.upper().replace('.JSON','')}_RANK_URL"
        updates[env] = f"{base}/data/{fname}"
    n = len(updates)
    rewrite_env_file(updates)
    if restart:
        _schedule_restart()
    return {"ok": True, "enabled": n, "restarting": restart,
            "message": f"已填入 {n} 个平台数据源（{base}/data/...）。保存后重启即生效。"}


@app.post(
    "/api/v1/settings/enable-preset",
    summary="一键启用预置数据（免配置）",
    description="把 7 大平台的榜单数据源一键切到内置预置样例（客户不配置 API 也能看到数据）；有官方凭证后可再替换。",
    tags=["设置"],
)
@app.post(
    "/api/v1/配置/启用预置数据",
    summary="一键启用预置数据（免配置）",
    description="中文路径别名，等价于 POST /api/v1/settings/enable-preset。",
    tags=["设置"],
)
def settings_enable_preset(restart: bool = True) -> dict:
    from ..config import BASE_DIR, rewrite_env_file
    from ..preset_data import FILE_MAP, ensure_preset_files, preset_dir

    made = ensure_preset_files(BASE_DIR)
    updates = {}
    ok = 0
    for env, fname in FILE_MAP.items():
        if (preset_dir(BASE_DIR) / fname).exists():
            updates[f"SHOPMONITOR_{env.upper()}_RANK_URL"] = f"data/预置数据/{fname}"
            ok += 1
    rewrite_env_file(updates)
    if restart:
        _schedule_restart()
    return {
        "ok": ok > 0,
        "enabled": ok,
        "generated": made,
        "restarting": restart,
        "message": f"已启用 {ok} 个平台的预置数据（免配置）。服务重启后榜单即显示预置数据；有官方凭证后可在配置中心替换。",
    }


@app.post(
    "/api/v1/settings/test-notify",
    summary="测试通知通道",
    description="用当前输入的通知配置发送一条测试消息（Webhook/邮件/Telegram），返回各通道是否成功。",
    tags=["设置"],
)
@app.post(
    "/api/v1/配置/测试通知",
    summary="测试通知通道",
    description="中文路径别名，等价于 POST /api/v1/settings/test-notify。",
    tags=["设置"],
)
def settings_test_notify(body: dict = {}) -> dict:
    from .. import notify as nt

    result = {
        "webhook": nt.test_webhook(str(body.get("webhook_url") or "")),
        "email": nt.test_email(
            str(body.get("email_host") or ""),
            int(body.get("email_port") or 465),
            str(body.get("email_user") or ""),
            str(body.get("email_pass") or ""),
            str(body.get("email_from") or ""),
            str(body.get("email_to") or ""),
        ),
        "telegram": nt.test_telegram(str(body.get("telegram_token") or ""),
                                     str(body.get("telegram_chat_id") or "")),
    }
    ok = [n for n, r in result.items() if r.get("ok")]
    channels = {k: bool(v.get("ok")) for k, v in result.items()}
    if ok:
        message = "发送成功：" + "、".join("Webhook" if x == "webhook" else "邮件" if x == "email" else "Telegram" for x in ok)
    else:
        message = "全部失败，详见各通道错误"
    return {"ok": bool(ok), "channels": channels, "details": result, "message": message}


@app.get(
    "/api/v1/tools/competition",
    summary="类目竞争度分析",
    description="用榜单数据计算类目竞争度：卖家数/头部销量集中度/价格离散度/评分门槛 -> 竞争度指数与蓝海/红海结论。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/竞争度分析",
    summary="类目竞争度分析",
    description="中文路径别名，等价于 /api/v1/tools/competition。",
    tags=["选品工具"],
)
def tools_competition(
    platform: str = Query("mock", description="平台 key"),
    category: str = Query("数码", description="类目/关键词"),
    limit: int = Query(100, ge=30, le=200),
) -> dict:
    import statistics

    adapter = get_adapter(platform)
    cat = category or adapter.default_category
    try:
        items = _resolve_items(adapter, cat, limit)
        source = "live"
    except CollectorError:
        items = MockAdapter(platform=platform).fetch_rank(category=cat, limit=limit)
        source = "mock"

    prices = [p.price for p in items if p.price is not None]
    sellers: dict = {}
    for p in items:
        s = (p.shop_name or "未知店铺").strip()
        sellers.setdefault(s, []).append(p)

    sales_list = [p.sales or 0 for p in items]
    total_sales = sum(sales_list)
    top10_sales = sum(sorted(sales_list, reverse=True)[:10])
    top10_share = round(top10_sales / total_sales * 100, 1) if total_sales else None

    avg_price = round(statistics.mean(prices), 2) if prices else None
    median_price = round(statistics.median(prices), 2) if prices else None
    cv = round(statistics.pstdev(prices) / statistics.mean(prices), 2) if len(prices) > 1 and statistics.mean(prices) else None
    ratings = [p.rating for p in items if p.rating]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

    n_sellers = len(sellers)
    score = 10.0
    score += min(n_sellers / 30, 1) * 30
    if cv is not None:
        score += (1 - min(cv / 0.5, 1)) * 20
    if top10_share is not None:
        score += top10_share / 100 * 25
    if avg_rating:
        score += min(max(avg_rating - 3.5, 0) / 1.5, 1) * 15
    score = round(min(max(score, 0), 100), 1)
    level = "蓝海" if score < 40 else ("中等竞争" if score < 65 else "红海")
    level_color = "蓝海" if score < 40 else ("中等" if score < 65 else "红海")

    top_sellers = sorted(sellers.items(), key=lambda kv: -len(kv[1]))[:8]
    return {
        "platform": platform, "category": cat, "source": source,
        "total": len(items), "priced": len(prices),
        "seller_count": n_sellers,
        "avg_price": avg_price, "median_price": median_price, "price_cv": cv,
        "top10_sales_share": top10_share, "avg_rating": avg_rating,
        "score": score, "level": level,
        "note": ("卖家少/价格带分散/头部集中度低 => 竞争低，蓝海机会；"
                 "卖家多/价格战/头部集中 => 红海，谨慎切入"),
        "top_sellers": [{"shop": k, "products": len(v),
                         "avg_price": round(sum(p.price or 0 for p in v) / len(v), 2) if v else None}
                        for k, v in top_sellers],
    }


@app.get(
    "/api/v1/tools/shop-dynamics",
    summary="竞品店动态时间线",
    description="把监控中商品的变化（新品上榜/降价/涨价/销量飙升/排名变动）汇总成时间线，跟踪竞品动向。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/竞品动态",
    summary="竞品店动态时间线",
    description="中文路径别名，等价于 /api/v1/tools/shop-dynamics。",
    tags=["选品工具"],
)
def tools_shop_dynamics(
    platform: str = Query("", description="按平台过滤，留空=全部"),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    from .. import cache as _cache

    events = []
    try:
        mv = _cache.recent_movers(limit=limit)
    except Exception:  # noqa: BLE001
        mv = {}
    for x in mv.get("drops", []):
        if platform and x.get("platform") != platform:
            continue
        events.append({"time": x.get("checked_at") or "", "type": "降价",
                       "title": x.get("title"), "detail": f"¥{x.get('price_now')}（{x.get('price_change_pct')}%）"})
    for x in mv.get("rises", []):
        if platform and x.get("platform") != platform:
            continue
        events.append({"time": x.get("checked_at") or "", "type": "涨价",
                       "title": x.get("title"), "detail": f"¥{x.get('price_now')}（+{x.get('price_change_pct')}%）"})
    for x in mv.get("sales_surges", []):
        if platform and x.get("platform") != platform:
            continue
        events.append({"time": x.get("checked_at") or "", "type": "销量飙升",
                       "title": x.get("title"), "detail": f"销量 +{x.get('sales_delta')}"})
    for x in mv.get("drops", []) + mv.get("rises", []):
        if platform and x.get("platform") != platform:
            continue
        if x.get("rank_delta"):
            events.append({"time": x.get("checked_at") or "", "type": "排名",
                           "title": x.get("title"),
                           "detail": f"排名 {'↑' if x.get('rank_delta') > 0 else '↓'} {abs(x.get('rank_delta'))} 名"})
    try:
        na_items = _cache.recent_new_arrivals(days=days, limit=limit)
    except Exception:  # noqa: BLE001
        na_items = []
    for x in na_items or []:
        if platform and x.get("platform") != platform:
            continue
        events.append({"time": x.get("crawled_at") or x.get("created_at") or "", "type": "新品上榜",
                       "title": x.get("product_id") or x.get("title") or "", "detail": f"平台 {x.get('platform')}"})

    events.sort(key=lambda e: e["time"], reverse=True)
    return {"count": len(events), "events": events[:limit],
            "note": "来自监控快照：先添加关注并运行巡检后自动积累"}


@app.post(
    "/api/v1/monitor/period-report",
    summary="生成周报/月报",
    description="生成周期报告（week=周报 / month=月报）：告警统计 + 关注商品涨跌 + 热搜 + 大盘，落盘并返回路径。",
    tags=["报告"],
)
@app.post(
    "/api/v1/监控/周期报告",
    summary="生成周报/月报",
    description="中文路径别名，等价于 POST /api/v1/monitor/period-report。",
    tags=["报告"],
)
def monitor_period_report_generate(period: str = Query("week", pattern="^(week|month)$"), push: bool = False) -> dict:
    from ..daily_report import build_period_report, period_report_path
    md = build_period_report(period=period)
    p = period_report_path(period)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    return {"period": period, "path": str(p), "chars": len(md)}


@app.get(
    "/api/v1/monitor/period-report",
    summary="查看周报/月报",
    description="返回最新周报/月报 Markdown（未生成返回 404）。",
    tags=["报告"],
)
@app.get(
    "/api/v1/监控/周期报告",
    summary="查看周报/月报",
    description="中文路径别名。",
    tags=["报告"],
)
def monitor_period_report_view(period: str = Query("week", pattern="^(week|month)$"),
                                 fmt: str = Query("md", pattern="^(md|pdf)$")) -> Response:
    from ..daily_report import period_report_path
    from ..report import md_to_pdf
    p = period_report_path(period)
    if not p.exists():
        raise HTTPException(404, detail="周期报告尚未生成，请先 POST /api/v1/监控/周期报告")
    md = p.read_text(encoding="utf-8")
    if fmt == "pdf":
        import os
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), f"period_{int(time.time())}.pdf")
        md_to_pdf(md, tmp, title="电商监控" + ("月报" if period == "month" else "周报"))
        with open(tmp, "rb") as f:
            content = f.read()
        os.unlink(tmp)
        return Response(content, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=period.pdf"})
    return Response(md, media_type="text/markdown; charset=utf-8")


@app.get(
    "/api/v1/monitor/movers",
    summary="今日变动榜",
    description="从监控快照计算今日降价榜/涨价榜/销量飙升榜。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/变动榜",
    summary="今日变动榜",
    description="中文路径别名，等价于 /api/v1/monitor/movers。",
    tags=["监控"],
)
def monitor_movers(limit: int = Query(10, ge=1, le=50)) -> dict:
    from .. import cache as _cache
    return _cache.recent_movers(limit=limit)


# ---------------- 潜力商品筛选器 ----------------
@app.get(
    "/api/v1/tools/filter",
    summary="潜力商品筛选",
    description="拉取榜单后按价格区间/最低销量/评分/评论/排名/促销/库存过滤，并按潜力分排序。",
    tags=["选品工具"],
)
@app.get(
    "/api/v1/工具/筛选",
    summary="潜力商品筛选",
    description="中文路径别名，等价于 /api/v1/tools/filter。",
    tags=["选品工具"],
)
def tools_filter(
    platform: str,
    category: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    min_sales: Optional[int] = None,
    min_rating: Optional[float] = None,
    min_reviews: Optional[int] = None,
    max_rank: Optional[int] = None,
    only_promo: bool = False,
    only_in_stock: bool = False,
    limit: int = Query(50, ge=1, le=100),
    profit_cost_rate: float = Query(0.4, ge=0, le=1, description="预估采购成本占售价比例（毛利估算用），如 0.4=40%"),
    profit_shipping: float = Query(0.0, ge=0, description="预估运费（元/件，毛利估算用）"),
    profit_acos: float = Query(0.0, ge=0, le=1, description="预估广告费 ACOS（毛利估算用），如 0.12=12%"),
    profit_duty_rate: float = Query(0.0, ge=0, le=0.5, description="预估进口关税率（占成本比例）"),
    profit_return_rate: float = Query(0.0, ge=0, le=0.5, description="预估退货率"),
    profit_min: Optional[float] = Query(None, description="最低预估毛利（元），只保留毛利不低于此值的商品"),
    fmt: str = Query("json", pattern="^(json|md|csv|xlsx|pdf)$", description="json=接口数据；md/csv/xlsx/pdf=选品毛利表导出"),
) -> dict:
    adapter = get_adapter(platform)
    cat = category or adapter.default_category
    try:
        items = _resolve_items(adapter, cat, 100)
        source = "live"
    except CollectorError:
        items = MockAdapter(platform=platform).fetch_rank(category=cat, limit=100)
        source = "mock"

    def _ok(p) -> bool:
        if price_min is not None and (p.price is None or p.price < price_min):
            return False
        if price_max is not None and (p.price is None or p.price > price_max):
            return False
        if min_sales is not None and (p.sales is None or p.sales < min_sales):
            return False
        if min_rating is not None and (p.rating is None or p.rating < min_rating):
            return False
        if min_reviews is not None and (p.review_count is None or p.review_count < min_reviews):
            return False
        if max_rank is not None and (p.rank is None or p.rank > max_rank):
            return False
        if only_promo and not p.is_promo:
            return False
        if only_in_stock and p.stock_status not in ("现货", None):
            return False
        return True

    from ..insights import COMMISSION_RATES, estimate_item_profit
    comm = COMMISSION_RATES.get(platform, 0.05)
    out = []
    for p in items:
        if not _ok(p):
            continue
        score = 0.0
        if p.sales:
            score += min(p.sales / 100, 50)
        if p.rating:
            score += p.rating * 10
        if p.rank:
            score += max(0, 20 - p.rank)
        d = p.model_dump(mode="json")
        d["score"] = round(score, 1)
        est, margin = estimate_item_profit(
            d.get("price"), platform, profit_cost_rate, profit_shipping, profit_acos,
            profit_duty_rate, profit_return_rate)
        d["estimated_profit"] = est
        d["estimated_margin"] = margin
        if profit_min is not None and (est is None or est < profit_min):
            continue
        out.append(d)
    out.sort(key=lambda x: -x["score"])
    params = {
        "commission_rate": comm, "other_rate": 0.01,
        "cost_rate": profit_cost_rate, "shipping": profit_shipping, "acos": profit_acos,
        "duty_rate": profit_duty_rate, "return_rate": profit_return_rate,
    }
    items = out[:limit]
    if fmt == "json":
        return {
            "platform": platform, "category": cat, "source": source,
            "count": len(out), "estimated_profit_params": params, "items": items,
        }
    # 选品毛利表导出
    from ..report import export_profit_table
    if fmt == "csv":
        content = export_profit_table(items, "csv")
        return Response(content, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=profit_table.csv"})
    if fmt == "pdf":
        import os
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), f"profit_{int(time.time())}.pdf")
        export_profit_table(items, "pdf", path=tmp)
        with open(tmp, "rb") as f:
            data = f.read()
        os.unlink(tmp)
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=profit_table.pdf"})
    if fmt == "xlsx":
        import os
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), f"profit_{int(time.time())}.xlsx")
        export_profit_table(items, "xlsx", path=tmp)
        with open(tmp, "rb") as f:
            data = f.read()
        os.unlink(tmp)
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=profit_table.xlsx"})
    return Response(export_profit_table(items, "md"),
                    media_type="text/markdown; charset=utf-8")


# ---------------- 关注商品总览 ----------------
@app.get(
    "/api/v1/monitor/overview",
    summary="关注商品总览",
    description="所有启用关注项下的商品最新状态（价格/销量/排名/库存），一表看全。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/关注总览",
    summary="关注商品总览",
    description="中文路径别名，等价于 /api/v1/monitor/overview。",
    tags=["监控"],
)
def monitor_overview() -> dict:
    from .. import cache as _cache
    rows = _cache.watch_overview()
    return {"count": len(rows), "items": rows}


# ---------------- 热搜词热度趋势 ----------------
@app.get(
    "/api/v1/uumit/hot-trend",
    summary="热搜词热度趋势",
    description="近 N 天热搜词热度变化（需先多次拉取热搜自动积累快照）：最新热度/首日热度/变化率/排名。platform=douyin|baidu_realtime 等。",
    tags=["UUMit 热搜选词"],
)
@app.get(
    "/api/v1/uumit/热搜趋势",
    summary="热搜词热度趋势",
    description="中文路径别名，等价于 /api/v1/uumit/hot-trend。",
    tags=["UUMit 热搜选词"],
)
def uumit_hot_trend(platform: str = "douyin", days: int = Query(7, ge=1, le=30), limit: int = Query(10, ge=1, le=50)) -> dict:
    from .. import cache as _cache
    return _cache.hot_trend(platform=platform, days=days, limit=limit)


# ---------------- 批量导入监控 ----------------
@app.post(
    "/api/v1/monitor/batch-import",
    summary="批量导入关注",
    description="粘贴商品链接（每行一个，自动识别平台与 ID；也支持 平台:ID 格式；纯 ID 需指定 default_platform），批量添加 product 模式关注。",
    tags=["监控"],
)
@app.post(
    "/api/v1/监控/批量导入",
    summary="批量导入关注",
    description="中文路径别名，等价于 /api/v1/monitor/batch-import。",
    tags=["监控"],
)
def monitor_batch_import(body: dict = {}) -> dict:
    from ..batch_import import parse_product_lines

    text = (body.get("text") or "") if isinstance(body, dict) else ""
    default_platform = (body.get("default_platform") or "").strip() if isinstance(body, dict) else ""
    parsed = parse_product_lines(text, default_platform=default_platform)
    added, skipped = 0, []
    for item in parsed:
        plat, pid = item["platform"], item["product_id"]
        if not plat or not pid:
            skipped.append({**item, "status": item["source"]})
            continue
        wid = cache.add_watch(platform=plat, mode="product", product_id=pid, alias=pid)
        if wid:
            added += 1
        else:
            skipped.append({**item, "status": "add_failed"})
    return {"added": added, "skipped_count": len(skipped), "skipped": skipped[:20], "total": len(parsed)}


# ---------------- 设置：配置状态 + 数据源模板 ----------------
@app.get(
    "/api/v1/settings/status",
    summary="配置状态总览",
    description="各数据源/AI/推送是否已配置（只返回是否，不返回密钥），用于「设置」页一目了然。",
    tags=["设置"],
)
@app.get(
    "/api/v1/配置/状态",
    summary="配置状态总览",
    description="中文路径别名，等价于 /api/v1/settings/status。",
    tags=["设置"],
)
def settings_status() -> dict:
    from .. import config as cfg

    def skill_ok() -> bool:
        from pathlib import Path
        for p in ([Path(cfg.UUMIT_SKILL_DIR)] if cfg.UUMIT_SKILL_DIR else []) + [Path.home() / ".codex" / "skills" / "uumit-agent"]:
            if p and (p / "scripts" / "rest_request.js").exists():
                return True
        return False

    items = [
        {"key": "uumit", "name": "UUMit 免费数据", "configured": skill_ok(),
         "note": "大盘/热搜/联想词真实数据源（0 扣费）"},
        {"key": "jd_union", "name": "京东联盟 API", "configured": bool(cfg.JD_UNION_APP_KEY and cfg.JD_UNION_SECRET_KEY),
         "note": "官方 API；需在 union.jd.com 给应用开通 goods.query 权限"},
        {"key": "pdd", "name": "拼多多 数据源", "configured": bool(cfg.PDD_RANK_URL),
         "note": "自定义 JSON 数据源（当前已接）"},
        {"key": "jd", "name": "京东 自定义数据源", "configured": bool(cfg.JD_RANK_URL),
         "note": "SHOPMONITOR_JD_RANK_URL，JSON 榜单"},
        {"key": "douyin", "name": "抖音 数据源", "configured": bool(cfg.DOUYIN_RANK_URL),
         "note": "SHOPMONITOR_DOUYIN_RANK_URL；热搜已由 UUMit 提供"},
        {"key": "taobao", "name": "淘宝 数据源", "configured": bool(cfg.TAOBAO_COOKIE or cfg.TAOBAO_RANK_URL),
         "note": "登录 Cookie 或自定义 JSON"},
        {"key": "shopee", "name": "Shopee 数据源", "configured": bool(cfg.SHOPEE_COOKIE or cfg.SHOPEE_RANK_URL),
         "note": "登录 Cookie 或自定义 JSON"},
        {"key": "amazon", "name": "Amazon 数据源", "configured": bool(cfg.AMAZON_RANK_URL),
         "note": "自定义 JSON 或 PA-API"},
        {"key": "aliexpress", "name": "AliExpress 数据源", "configured": bool(cfg.ALIEXPRESS_RANK_URL),
         "note": "自定义 JSON 或官方 API"},
        {"key": "douyin_mall", "name": "抖音商城（抖店）官方 API", "configured": bool(cfg.DOUYIN_MALL_APP_ID and cfg.DOUYIN_MALL_SECRET),
         "note": "op.jinritemai.com 开放平台 AppID/Secret（需企业认证）"},
        {"key": "taobao_open", "name": "淘宝开放平台 API", "configured": bool(cfg.TAOBAO_APP_KEY and cfg.TAOBAO_APP_SECRET),
         "note": "open.taobao.com 应用 AppKey/Secret"},
        {"key": "pdd_open", "name": "拼多多开放平台 API", "configured": bool(cfg.PDD_CLIENT_ID and cfg.PDD_CLIENT_SECRET),
         "note": "open.pinduoduo.com 应用 ClientId/Secret"},
        {"key": "alibaba_open", "name": "1688 开放平台 API", "configured": bool(cfg.ALIBABA_APP_KEY and cfg.ALIBABA_APP_SECRET),
         "note": "open.1688.com 应用 AppKey/Secret"},
        {"key": "kuaishou_open", "name": "快手电商开放平台 API", "configured": bool(cfg.KUAISHOU_APP_KEY and cfg.KUAISHOU_APP_SECRET),
         "note": "open.kwaixiaodian.com 应用 AppKey/Secret"},        {"key": "tiktok_shop", "name": "TikTok Shop 官方 API", "configured": bool(cfg.TIKTOK_SHOP_APP_KEY and cfg.TIKTOK_SHOP_APP_SECRET),
         "note": "partner.tiktokshop.com 应用 AppKey/Secret（需商家授权）"},
        {"key": "amazon_open", "name": "Amazon PA-API 官方 API", "configured": bool(cfg.AMAZON_ACCESS_KEY and cfg.AMAZON_SECRET_KEY and cfg.AMAZON_PARTNER_TAG),
         "note": "webservices.amazon.com PA-API 5.0（需 AWS Key + 联盟 PartnerTag）"},
        {"key": "shopee_open", "name": "Shopee 开放平台官方 API", "configured": bool(cfg.SHOPEE_PARTNER_ID and cfg.SHOPEE_PARTNER_KEY),
         "note": "open.shopee.com 应用 PartnerKey + 商家授权"},
        {"key": "aliexpress_open", "name": "AliExpress 联盟官方 API", "configured": bool(cfg.ALIEXPRESS_OPEN_APP_KEY and cfg.ALIEXPRESS_OPEN_APP_SECRET),
         "note": "open.aliexpress.com 联盟应用 + 推广者授权"},
        {"key": "ai", "name": "AI 选品分析", "configured": bool(cfg.AI_LLM_API_KEY),
         "note": "豆包/智谱/通义/DeepSeek 任选（OpenAI 兼容）"},
        {"key": "webhook", "name": "告警推送 Webhook", "configured": bool(cfg.ALERT_WEBHOOK_URL),
         "note": "企业微信/钉钉/飞书机器人；留空则只本机记录"},
    ]
    return {"count": len(items), "configured": sum(1 for x in items if x["configured"]), "items": items}


@app.get(
    "/api/v1/settings/source-template",
    summary="数据源模板下载",
    description="下载自定义 JSON 数据源模板（数据源模板.json），按模板填平台榜单即可点亮真实数据。",
    tags=["设置"],
)
@app.get(
    "/api/v1/配置/数据源模板",
    summary="数据源模板下载",
    description="中文路径别名。",
    tags=["设置"],
)
def settings_source_template() -> Response:
    tpl = Path(__file__).resolve().parent.parent.parent / "数据源模板.json"
    if not tpl.exists():
        raise HTTPException(404, detail="数据源模板.json 不存在")
    return Response(
        tpl.read_text(encoding="utf-8"),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=source_template.json; filename*=UTF-8''%E6%95%B0%E6%8D%AE%E6%BA%90%E6%A8%A1%E6%9D%BF.json"
        },
    )


# ---------------- 新品上榜（竞品上新监控） ----------------
@app.get(
    "/api/v1/monitor/new-arrivals",
    summary="新品上榜榜",
    description="近期首次出现在监控榜中的商品（新品上榜，竞品上新监控）。",
    tags=["监控"],
)
@app.get(
    "/api/v1/监控/新品榜",
    summary="新品上榜榜",
    description="中文路径别名。",
    tags=["监控"],
)
def monitor_new_arrivals(days: int = Query(3, ge=1, le=30), limit: int = Query(20, ge=1, le=50)) -> dict:
    from .. import cache as _cache
    items = _cache.recent_new_arrivals(days=days, limit=limit)
    return {"count": len(items), "items": items}


# ---------------- 订阅套餐状态 ----------------
@app.get(
    "/api/v1/plan/status",
    summary="订阅套餐状态",
    description="当前套餐、限额与使用量（多用户订阅 MVP）。",
    tags=["设置"],
)
@app.get(
    "/api/v1/套餐/状态",
    summary="订阅套餐状态",
    description="中文路径别名。",
    tags=["设置"],
)
def plan_status() -> dict:
    from .. import config as cfg
    watches = len(cache.list_watches())
    return {
        "plan": cfg.PLAN_NAME,
        "limits": cfg.PLAN_LIMITS,
        "usage": {"watches": watches},
        "ai_enabled": cfg.PLAN_LIMITS["ai"],
        "upgrade_hint": "修改 配置文件.env 的 SHOPMONITOR_PLAN 即可切换套餐（free/pro/enterprise）",
    }


# ---------------- 在线配置中心（接口文档页直接配置，改完自动重启生效） ----------------
_CONFIG_UPDATE_ALLOWED = set()
from ..config import UI_CONFIG_SCHEMA  # noqa: E402
_CONFIG_UPDATE_ALLOWED = set(UI_CONFIG_SCHEMA.keys())


@app.get(
    "/api/v1/settings/editable",
    summary="可配置项列表",
    description="返回可通过网页修改的配置项（名称/分类/当前值掩码/提示），驱动接口文档页的配置中心。",
    tags=["设置"],
)
@app.get(
    "/api/v1/配置/可配置项",
    summary="可配置项列表",
    description="中文路径别名。",
    tags=["设置"],
)
def settings_editable() -> dict:
    from ..config import ui_config_value
    items = []
    for key, (name, cat, secret, hint) in UI_CONFIG_SCHEMA.items():
        items.append({"key": key, "name": name, "category": cat, "secret": secret, "hint": hint,
                      "value": ui_config_value(key)})
    return {"count": len(items), "items": items}


@app.post(
    "/api/v1/settings/save",
    summary="保存配置",
    description="保存配置项到 配置文件.env，并自动重启服务生效（restart=false 只保存不重启，用于调试）。",
    tags=["设置"],
)
@app.post(
    "/api/v1/配置/保存",
    summary="保存配置",
    description="中文路径别名。",
    tags=["设置"],
)
def settings_save(body: dict = {}, restart: bool = True) -> dict:
    from ..config import rewrite_env_file

    raw = body.get("items") if isinstance(body, dict) else None
    if not isinstance(raw, list):
        raise HTTPException(400, detail="body 需为 {items: [{key, value}, ...]}")
    updates = {}
    for it in raw:
        key = str(it.get("key") or "").strip()
        value = it.get("value")
        if key not in _CONFIG_UPDATE_ALLOWED:
            raise HTTPException(400, detail=f"不允许修改的配置项：{key}")
        updates[key] = "" if value is None else str(value).strip()
    rewrite_env_file(dict(updates))
    if restart:
        _schedule_restart()
    return {"saved": list(updates.keys()), "restarting": restart, "message": "已保存，服务将自动重启（约 3 秒）" if restart else "已保存（未重启，重启后生效）"}


def _schedule_restart() -> None:
    import os
    import subprocess
    import sys
    import threading

    def _do() -> None:
        base = str(Path(__file__).resolve().parent.parent.parent)
        code = (
            "import subprocess,sys,time;time.sleep(2.5);"
            f"subprocess.Popen([sys.executable,'-X','utf8','run_api.py'],cwd=r'{base}');"
        )
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen([sys.executable, "-c", code], creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)
        try:
            os.kill(os.getpid(), 9)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_do, daemon=True).start()


@app.post(
    "/api/v1/settings/test-source",
    summary="测试数据源",
    description="验证一个自定义 JSON 数据源地址是否可用（返回商品条数）。",
    tags=["设置"],
)
@app.post(
    "/api/v1/配置/测试数据源",
    summary="测试数据源",
    description="中文路径别名。",
    tags=["设置"],
)
def settings_test_source(body: dict = {}) -> dict:
    import json as _json
    from ..http_utils import read_data_source
    from ..collectors.env_json import _extract_items

    url = ((body.get("url") or "") if isinstance(body, dict) else "").strip()
    if not url:
        raise HTTPException(400, detail="url 不能为空")
    try:
        raw = read_data_source(url)
        data = _json.loads(raw)
        items = _extract_items(data)
        if not items:
            return {"ok": False, "message": "数据源返回 0 个商品（检查是否为 items 数组格式）"}
        return {"ok": True, "count": len(items), "message": f"可用：解析到 {len(items)} 个商品"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"不可用：{str(e)[:150]}"}


@app.post(
    "/api/v1/settings/test-ai",
    summary="测试 AI Key",
    description="用当前（或传入的）AI 配置发一条极短请求，验证 Key/模型是否可用。",
    tags=["设置"],
)
@app.post(
    "/api/v1/配置/测试AI",
    summary="测试 AI Key",
    description="中文路径别名。",
    tags=["设置"],
)
def settings_test_ai(body: dict = {}) -> dict:
    from .. import ai_analysis

    key = ((body.get("api_key") or "") if isinstance(body, dict) else "").strip()
    base = ((body.get("base_url") or "") if isinstance(body, dict) else "").strip()
    model = ((body.get("model") or "") if isinstance(body, dict) else "").strip()
    if not key:
        raise HTTPException(400, detail="请先填 AI Key")
    try:
        # 用传入的配置做一次极短调用
        text = ai_analysis._call_llm_with(
            prompt="回复两个字：正常", api_key=key, base_url=base or None, model=model or None, timeout=30
        )
        return {"ok": True, "message": f"AI 可用，返回：{text[:30]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"AI 不可用：{str(e)[:150]}"}


@app.post(
    "/api/v1/settings/test-webhook",
    summary="测试 Webhook",
    description="向企业微信/钉钉/飞书机器人发送一条测试消息。",
    tags=["设置"],
)
@app.post(
    "/api/v1/配置/测试Webhook",
    summary="测试 Webhook",
    description="中文路径别名。",
    tags=["设置"],
)
def settings_test_webhook(body: dict = {}) -> dict:
    import urllib.request

    url = ((body.get("url") or "") if isinstance(body, dict) else "").strip()
    if not url:
        raise HTTPException(400, detail="请先填 Webhook 地址")
    payload = __import__("json").dumps(
        {"msgtype": "text", "text": {"content": "【ShopMonitor】Webhook 配置测试：发送成功 ✅"}},
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=8)
        return {"ok": True, "message": "Webhook 测试消息已发送"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"发送失败：{str(e)[:150]}"}

