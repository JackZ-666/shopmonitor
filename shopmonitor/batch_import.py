# -*- coding: utf-8 -*-
"""批量导入：粘贴商品链接/ID 批量添加监控关注（对标盯价哨兵一键加监控）。"""
from __future__ import annotations

import re
from typing import List

# 平台域名 -> 平台标识
_DOMAINS = {
    "jd.com": "jd",
    "taobao.com": "taobao",
    "tmall.com": "taobao",
    "pinduoduo.com": "pdd",
    "yangkeduo.com": "pdd",
    "jinritemai.com": "douyin",
    "douyin.com": "douyin",
    "shopee.com": "shopee",
    "shopee.cn": "shopee",
    "shopee.sg": "shopee",
    "shopee.tw": "shopee",
    "shopee.com.my": "shopee",
    "shopee.co.th": "shopee",
    "shopee.vn": "shopee",
    "shopee.ph": "shopee",
    "shopee.co.id": "shopee",
    "amazon.com": "amazon",
    "amazon.co.uk": "amazon",
    "amazon.de": "amazon",
    "amazon.fr": "amazon",
    "amazon.it": "amazon",
    "amazon.es": "amazon",
    "amazon.ca": "amazon",
    "amazon.co.jp": "amazon",
    "amazon.com.mx": "amazon",
    "aliexpress.com": "aliexpress",
    "aliexpress.ru": "aliexpress",
}

# 各平台商品 ID 提取规则（host 片段 -> (正则, 组)）
_ID_PATTERNS = [
    ("jd", r"item\.jd\.com/(\d+)", 1),
    ("taobao", r"[?&]id=(\d+)", 1),
    ("pdd", r"goods_id=(\d+)", 1),
    ("pdd", r"/goods/(\d+)", 1),
    ("douyin", r"[?&](?:item_id|product_id|id)=(\d+)", 1),
    ("shopee", r"/product/[^/]+/(\d+)", 1),
    ("amazon", r"/(?:dp|gp/product)/([A-Z0-9]{10})", 1),
    ("aliexpress", r"/item/(\d+)", 1),
]


def parse_platform(url: str) -> str:
    """从 URL 推断平台。"""
    low = url.lower()
    for dom, plat in _DOMAINS.items():
        if dom in low:
            return plat
    return ""


def extract_product_id(platform: str, url: str) -> str:
    """从 URL 提取商品 ID（按平台规则）。"""
    for plat, pat, grp in _ID_PATTERNS:
        if plat != platform:
            continue
        m = re.search(pat, url, re.IGNORECASE)
        if m:
            return m.group(grp)
    return ""


def parse_product_lines(text: str, default_platform: str = "") -> List[dict]:
    """解析多行输入 -> [{platform, product_id, source}]。

    支持：
    - 商品链接（自动识别平台并提取 ID）
    - 「平台:ID」格式（如 jd:123456 / taobao:789）
    - 纯 ID 行：需传 default_platform 才会采纳
    无法识别的一律跳过并标注。
    """
    out: List[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # 平台:ID 显式格式（仅当不含 :// 时，避免误吞链接）
        if ":" in line and "://" not in line:
            plat, _, pid = line.partition(":")
            plat, pid = plat.strip().lower(), pid.strip()
            if plat and pid:
                out.append({"platform": plat, "product_id": pid, "source": "explicit"})
                continue
        if line.startswith(("http://", "https://")):
            plat = parse_platform(line)
            if not plat:
                out.append({"platform": "", "product_id": line[:60], "source": "unrecognized_url"})
                continue
            pid = extract_product_id(plat, line)
            if not pid:
                out.append({"platform": plat, "product_id": line[:60], "source": "no_id_found"})
                continue
            out.append({"platform": plat, "product_id": pid, "source": "url"})
            continue
        # 纯 ID 行
        if default_platform:
            out.append({"platform": default_platform, "product_id": line, "source": "plain"})
        else:
            out.append({"platform": "", "product_id": line, "source": "no_platform"})
    return out
