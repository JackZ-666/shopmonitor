"""UUMit 免费数据源集成。

通过本机已安装的 uumit-agent 技能（rest_request.js）调用 UUMit 平台：
- 免费发现（smart-invoke mode=preview，不扣费）
- 只自动调用 price_ut=0 的免费数据 API；付费接口一律返回 needs_confirmation，绝不静默扣费
- 不输出任何 API Key / Token 等敏感字段

依赖：本机已安装并授权 uumit-agent 技能（C:\\Users\\HP\\.codex\\skills\\uumit-agent）。
"""
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import UUMIT_SKILL_DIR

_SENSITIVE_KEYS = {"api_key", "apikey", "token", "secret", "access_token", "confirm_token", "credential"}


class UumitError(RuntimeError):
    pass


def _skill_dir() -> Path:
    candidates: List[Path] = []
    if UUMIT_SKILL_DIR:
        candidates.append(Path(UUMIT_SKILL_DIR))
    candidates.append(Path.home() / ".codex" / "skills" / "uumit-agent")
    for p in candidates:
        if (p / "scripts" / "rest_request.js").exists():
            return p
    raise UumitError(
        "未找到 uumit-agent 技能目录（请先安装并授权，或设置环境变量 UUMIT_SKILL_DIR）"
    )


def _run_rest(
    method: str,
    path: str,
    body: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: int = 90,
) -> dict:
    skill = _skill_dir()
    node = shutil.which("node") or "node"
    args = [node, str(skill / "scripts" / "rest_request.js"), method, path]
    for k, v in (params or {}).items():
        args += ["--param", str(k), str(v)]
    tmp: Optional[Path] = None
    if body is not None:
        tmp = Path(tempfile.gettempdir()) / f"uumit_body_{uuid.uuid4().hex}.json"
        tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        args += ["--file", str(tmp)]
    try:
        proc = subprocess.run(args, capture_output=True, timeout=timeout, cwd=str(skill))
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise UumitError((err or out).strip()[:500] or "UUMit 调用失败")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:  # noqa: BLE001
        raise UumitError(f"UUMit 返回非 JSON: {e}") from e


def _check(resp: dict) -> dict:
    if resp.get("code") != 0:
        raise UumitError(f"UUMit 错误 {resp.get('code')}: {resp.get('message')}")
    return resp.get("data") or {}


def _sanitize(obj: Any) -> Any:
    """递归剔除敏感字段，防止 Key 泄漏。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                continue
            out[k] = _sanitize(v)
        return out
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    return obj


def _to_float_price(price) -> float:
    try:
        return float(price or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------- 只读状态 ----------------
def account_status() -> dict:
    """钱包快照（只读）。"""
    d = _check(_run_rest("GET", "/api/v1/wallet"))
    ut = d.get("ut") or {}
    cash = d.get("cash") or {}
    return {
        "connected": True,
        "ut_balance": ut.get("balance"),
        "ut_available": ut.get("available"),
        "ut_withdrawable": ut.get("withdrawable_balance"),
        "cash_balance": cash.get("balance"),
    }


def free_credits_summary() -> dict:
    """星火计划 + 已购包 AI 额度汇总（只读，敏感字段已剔除）。"""
    try:
        d = _check(_run_rest("GET", "/api/v1/llm/my-credits/summary"))
        return _sanitize(d)
    except UumitError:
        return {"available": False, "reason": "星火计划额度查询暂不可用"}


# ---------------- 免费能力发现 ----------------
_FALLBACK_INTENTS = [
    "查询电商平台商品价格与销量数据",
    "电商商品销量与价格数据",
    "电商销售额销量趋势分析",
    "选品与竞品数据",
    "电商订单与成交额数据",
]


def discover_free_capabilities(intent: Optional[str] = None, top: int = 10) -> List[dict]:
    """按意图 preview 发现免费（price_ut=0）数据能力，不扣费；多意图兜底。"""
    intents: List[str] = []
    if intent:
        intents.append(intent)
    for i in _FALLBACK_INTENTS:
        if i not in intents:
            intents.append(i)

    out: List[dict] = []
    seen: set = set()
    for it in intents:
        if len(out) >= top:
            break
        try:
            body = {"intent": it, "mode": "preview", "auto_spend_max_ut": 0}
            d = _check(_run_rest("POST", "/api/v1/capability-runtime/smart-invoke", body=body))
        except UumitError:
            continue
        candidates = []
        selected = d.get("selected_capability")
        if isinstance(selected, dict):
            candidates.append(selected)
        for alt in d.get("alternatives") or []:
            if isinstance(alt, dict):
                candidates.append(alt)
        for c in candidates:
            price = _to_float_price((c.get("pricing") or {}).get("price_ut"))
            if price != 0:
                continue
            api_id = (c.get("metadata") or {}).get("data_api_id")
            if not api_id:
                continue
            if api_id in seen:
                continue
            seen.add(api_id)
            out.append(
                {
                    "capability_id": c.get("capability_id"),
                    "title": c.get("title"),
                    "description": c.get("description"),
                    "category": c.get("category"),
                    "price_ut": 0,
                    "api_id": api_id,
                    "invoke_protocol": c.get("invoke_protocol"),
                    "can_direct_invoke": (c.get("routing_hint") or {}).get("can_direct_invoke"),
                    "input_schema": _sanitize(c.get("input_schema") or {}),
                }
            )
            if len(out) >= top:
                break
    return out


# ---------------- 数据 API ----------------
def data_api_detail(api_id: str) -> dict:
    d = _check(_run_rest("GET", f"/api/v1/data-marketplace/{api_id}"))
    return {
        "api_id": d.get("id"),
        "name": d.get("name"),
        "description": d.get("description"),
        "category": d.get("custom_category") or d.get("category"),
        "owner": d.get("owner_nickname"),
        "price_ut": _to_float_price(d.get("price_ut")),
        "request_schema": d.get("request_schema"),
        "response_schema": d.get("response_schema"),
        "example_response": d.get("example_response"),
    }


def call_free_data_api(api_id: str, body: dict) -> dict:
    """只调用 price_ut=0 的免费数据 API；付费接口返回 needs_confirmation。

    实测（2026-08）：数据广场 /call 对 GET 型上游要求把参数包在 {"params": {...}} 里，
    对其它上游两种写法均兼容，故统一用 {"params": body} 包装，确保全平台可调。
    """
    detail = _check(_run_rest("GET", f"/api/v1/data-marketplace/{api_id}"))
    price = _to_float_price(detail.get("price_ut"))
    if price != 0:
        return {
            "status": "needs_confirmation",
            "message": f"该数据 API 为付费接口（{price} UT），本套件只自动调用免费接口；如需付费请人工确认。",
            "price_ut": price,
        }
    resp = _run_rest("POST", f"/api/v1/data-marketplace/{api_id}/call", body={"params": body or {}})
    if resp.get("code") != 0:
        raise UumitError(f"UUMit 调用失败 {resp.get('code')}: {resp.get('message')}")
    d = resp.get("data") or {}
    return {
        "status": "ok",
        "api_id": api_id,
        "call_id": d.get("call_id"),
        "is_free": d.get("is_free", True),
        "charged_ut": d.get("charged_ut", "0"),
        "latency_ms": d.get("latency_ms"),
        "result": _sanitize(d.get("result")),
    }