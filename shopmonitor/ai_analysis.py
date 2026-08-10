# -*- coding: utf-8 -*-
"""AI 选品分析：大盘 + 热搜 + 联想词 + 趋势 -> 大模型生成选品建议。

- 大模型：任意 OpenAI 兼容 API（豆包火山方舟 / 智谱 GLM / 通义 DashScope / DeepSeek 等）
- 配置：AI_LLM_API_KEY / AI_LLM_BASE_URL / AI_LLM_MODEL（配置文件.env 或环境变量）
- 未配置 key 时返回 needs_key，绝不阻塞其它功能
- 数据来自 UUMit 免费接口（0 扣费），断网时降级为仅用可用部分
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import requests

from . import uumit_data
from .config import AI_LLM_API_KEY, resolve_llm_endpoint


def _fmt(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return "-"
    if v >= 1e8:
        return f"{v/1e8:.2f}亿"
    if v >= 1e4:
        return f"{v/1e4:.1f}万"
    return f"{v:,.0f}"


def _collect_context(keyword: str) -> Dict[str, Any]:
    """收集分析所需的实时数据（UUMit 免费，逐项容错）。"""
    ctx: Dict[str, Any] = {"keyword": keyword, "sections": {}}
    try:
        ov = uumit_data.market_overview()
        ctx["sections"]["大盘"] = (
            f"订单 {ov.get('order_count')}，用户 {ov.get('user_count')}，成交额 {_fmt(ov.get('total_amount'))}，"
            f"客单价 {_fmt(ov.get('avg_order_amount'))}，销量 {_fmt(ov.get('total_quantity'))}，"
            f"商品 {ov.get('product_count')}，类目 {ov.get('category_count')}，品牌 {ov.get('brand_count')}"
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        pf = uumit_data.platform_performance()
        rows = []
        for r in pf.get("items", []):
            rows.append(f"{r['platform']}(商品 {r['product_count']}，均价 {_fmt(r['avg_price'])}，销量 {_fmt(r['sales_count'])})")
        ctx["sections"]["平台"] = "；".join(rows)
    except Exception:  # noqa: BLE001
        pass
    try:
        hot = uumit_data.douyin_hot()
        ctx["sections"]["抖音热搜"] = "、".join(f"{it['title']}" for it in hot.get("items", [])[:8])
    except Exception:  # noqa: BLE001
        pass
    try:
        bd = uumit_data.baidu_hot(type_="realtime")
        ctx["sections"]["百度热搜"] = "、".join(f"{it['title']}" for it in bd.get("items", [])[:8])
    except Exception:  # noqa: BLE001
        pass
    if keyword:
        try:
            sg = uumit_data.taobao_suggest(keyword)
            ctx["sections"]["联想词"] = "、".join(f"{it['word']}" for it in sg.get("items", [])[:10])
        except Exception:  # noqa: BLE001
            pass
        try:
            tr = uumit_data.sales_trend(keyword=keyword, grain="month")
            items = tr.get("items", [])
            if items:
                recent = items[-6:]
                ctx["sections"]["趋势"] = "；".join(f"{it['period']}: {_fmt(it['total_amount'])}" for it in recent)
        except Exception:  # noqa: BLE001
            pass
    return ctx


def _build_prompt(ctx: Dict[str, Any]) -> str:
    kw = ctx.get("keyword") or "电商"
    parts = [f"我在做电商选品，目标是找到适合切入的细分方向。当前监控到的实时数据如下："]
    for name, val in ctx["sections"].items():
        parts.append(f"\n【{name}】{val}")
    parts.append(f"""
请基于以上实时数据，输出一份简洁的中文选品分析（Markdown 格式，控制在 400 字内），包含：
1. **大盘环境**：一句话总结当前电商大盘冷暖。
2. **热点机会**：从热搜中提炼 2-3 个与「{kw}」相关或可借势的方向。
3. **选品建议**：给出 3 个具体可落地的选品方向（含目标人群、价格带、平台建议）。
4. **关键词建议**：给出 5-8 个可用于搜索/标题的关键词（结合联想词）。
5. **风险提示**：1-2 条。
数据仅供参考，请明确标注"数据为监控快照，非官方口径"。
""")
    return "\n".join(parts)


def _call_llm_with(
    prompt: str, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 60
) -> str:
    """带参数覆盖的 LLM 调用（用于在线配置的"测试 AI"）。"""
    import requests as _req

    resolved_base = base_url or resolve_llm_endpoint()[0]
    resolved_model = model or resolve_llm_endpoint()[1]
    url = f"{resolved_base}/chat/completions"
    payload = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 20,
    }
    resp = _req.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_llm(prompt: str, timeout: int = 60) -> str:
    base, model = resolve_llm_endpoint()
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是资深电商选品分析师，输出简洁、可执行、不注水。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {AI_LLM_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def analyze_selection(keyword: str = "", fresh: bool = False) -> Dict[str, Any]:
    """执行一次 AI 选品分析。未配置 key 时返回 needs_key。"""
    keyword = (keyword or "").strip()
    ctx = _collect_context(keyword)
    if not AI_LLM_API_KEY:
        return {
            "status": "rule",
            "keyword": keyword,
            "analysis": _rule_analysis(ctx),
            "sections": ctx["sections"],
            "note": "未配置 AI Key，使用内置规则分析（数据为监控快照）",
            "hint": "配置 AI_LLM_API_KEY（豆包/智谱/通义/DeepSeek 任选）后可升级为大模型深度分析",
        }
    prompt = _build_prompt(ctx)
    t0 = time.time()
    try:
        text = _call_llm(prompt)
    except Exception as e:  # noqa: BLE001
        base, model = resolve_llm_endpoint()
        return {
            "status": "error",
            "message": f"AI 调用失败：{str(e)[:200]}（base={base} model={model}）",
            "latency_ms": int((time.time() - t0) * 1000),
        }
    return {
        "status": "ok",
        "keyword": keyword,
        "analysis": text,
        "latency_ms": int((time.time() - t0) * 1000),
        "model": resolve_llm_endpoint()[1],
        "sections": ctx["sections"],
        "note": "数据为监控快照，非官方口径",
    }


def _rule_analysis(ctx: Dict[str, Any]) -> str:
    """无 AI Key 时的规则化选品参考（基于大盘/热搜/联想词/趋势）。"""
    k = ctx.get("keyword") or "该品类"
    lines = [f"【{k} 选品参考】（规则分析，未配置 AI Key）", ""]
    sec = ctx.get("sections", {})
    if "联想词" in sec:
        words = [w for w in sec["联想词"].split("、") if w][:8]
        lines.append("搜索联想词：" + "、".join(words))
        if words:
            lines.append("优先布局：" + "、".join(words[:3]) + " 对应细分款。")
    if "抖音热搜" in sec:
        hot = [w for w in sec["抖音热搜"].split("、") if w][:4]
        lines.append("热点关联：" + "、".join(hot) + "，可结合热度过季/上新窗口切入。")
    if "平台" in sec:
        lines.append("平台行情：" + sec["平台"])
    if "大盘" in sec:
        lines.append("大盘：" + sec["大盘"])
    if "趋势" in sec:
        lines.append("近期趋势：" + sec["趋势"])
    lines.append("")
    lines.append("建议：优先选 搜索有量、竞争适中（蓝海指数高）的细分词；用毛利计算器按运营模式精算后再定价。")
    return "\n".join(lines)


def llm_status() -> Dict[str, Any]:
    """AI 配置状态（不泄露 key）。"""
    base, model = resolve_llm_endpoint()
    return {
        "configured": bool(AI_LLM_API_KEY),
        "base_url": base if AI_LLM_API_KEY else None,
        "model": model if AI_LLM_API_KEY else None,
        "hint": "未配置" if not AI_LLM_API_KEY else "已配置",
    }
