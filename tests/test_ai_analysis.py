# -*- coding: utf-8 -*-
"""AI 选品分析测试：未配置 key / 已配置走 mock LLM / prompt 组装 / 状态不泄 key。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from shopmonitor import ai_analysis


def _fixed_ctx():
    return {
        "keyword": "手机配件",
        "sections": {
            "大盘": "订单 382287，成交额 6.56亿，客单价 1716",
            "平台": "淘宝(商品 55196)；京东(商品 12474)",
            "抖音热搜": "今日立秋、台风实时路径",
            "百度热搜": "各美其美 美美与共",
            "联想词": "手机壳、手机膜",
            "趋势": "2024-12: 1.25亿",
        },
    }


def test_rule_fallback_when_not_configured(monkeypatch):
    monkeypatch.setattr(ai_analysis, "AI_LLM_API_KEY", "")
    monkeypatch.setattr(ai_analysis, "_collect_context", lambda keyword: {
        "keyword": keyword, "sections": {"联想词": "手机壳、手机膜、手机支架"}})
    r = ai_analysis.analyze_selection("手机")
    assert r["status"] == "rule"
    assert "手机壳" in r["analysis"]
    assert r["note"]


def test_analyze_ok_with_configured_key(monkeypatch):
    monkeypatch.setattr(ai_analysis, "AI_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(ai_analysis, "_collect_context", lambda kw: _fixed_ctx())
    monkeypatch.setattr(
        ai_analysis, "_call_llm",
        lambda prompt, timeout=60: "## 选品建议\n1. 手机壳（磁吸散热）\n2. 手机支架",
    )
    r = ai_analysis.analyze_selection("手机配件")
    assert r["status"] == "ok"
    assert "手机壳" in r["analysis"]
    assert r["keyword"] == "手机配件"
    assert r["latency_ms"] >= 0


def test_analyze_error_when_llm_fails(monkeypatch):
    monkeypatch.setattr(ai_analysis, "AI_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(ai_analysis, "_collect_context", lambda kw: _fixed_ctx())

    def boom(prompt, timeout=60):
        raise RuntimeError("上游超时")
    monkeypatch.setattr(ai_analysis, "_call_llm", boom)
    r = ai_analysis.analyze_selection("手机")
    assert r["status"] == "error"
    assert "AI 调用失败" in r["message"]


def test_build_prompt_contains_data():
    prompt = ai_analysis._build_prompt(_fixed_ctx())
    assert "手机配件" in prompt
    assert "大盘" in prompt
    assert "抖音热搜" in prompt
    assert "选品建议" in prompt


def test_llm_status_no_key_leak(monkeypatch):
    monkeypatch.setattr(ai_analysis, "AI_LLM_API_KEY", "sk-secret-123")
    st = ai_analysis.llm_status()
    assert st["configured"] is True
    assert "sk-secret" not in str(st)
