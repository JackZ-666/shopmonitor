# -*- coding: utf-8 -*-
"""生成无服务器数据包（方案E）：GitHub Actions 定时跑，输出 webdata/ 供 GitHub Pages 托管。

- 官方 API 凭证可用（从环境变量/GitHub Secrets 注入）-> 用官方适配器拉真实数据
- 否则 -> 用预置数据兜底
客户在配置中心填 GitHub Pages 地址即可（或点「一键填数据包」）。
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 平台 -> 官方适配器 key（能个人/联盟申请的真实数据源）
PLATFORM_MAP = {
    "jd": "jd_union",
    "taobao": "taobao_open",
    "pdd": "pdd_open",
    "amazon": "amazon_open",
    "aliexpress": "aliexpress_open",
    "shopee": "shopee_open",
    "douyin": None,
}


def _to_item(p, rank):
    return {
        "product_id": p.product_id, "title": p.title, "price": p.price,
        "original_price": p.original_price, "sales": p.sales,
        "sales_text": f"销量 {p.sales}" if p.sales is not None else None,
        "rating": p.rating, "review_count": p.review_count,
        "stock_status": p.stock_status, "promo_text": p.promo_text,
        "is_promo": p.is_promo, "shop_name": p.shop_name,
        "shop_rating": p.shop_rating, "rank": rank, "category": "数据包",
        "url": p.url, "image": p.image,
    }


def _preset_rows(platform):
    from shopmonitor.preset_data import PRESET_PRODUCTS
    rows = []
    for i, (pid, title, price, sales, shop, url) in enumerate(PRESET_PRODUCTS[platform], start=1):
        rows.append({
            "product_id": pid, "title": title, "price": price,
            "original_price": round(price * 1.35, 2), "sales": sales,
            "sales_text": f"销量 {sales}", "rating": 4.7, "review_count": int(sales * 0.3),
            "stock_status": "现货", "is_promo": i <= 2, "promo_text": "限时折扣" if i <= 2 else None,
            "shop_name": shop, "shop_rating": 4.8, "rank": i, "category": "数据包", "url": url,
        })
    return rows


# 生成器关心的密钥环境变量（用于诊断哪些已配置）
KNOWN_KEYS = [
    "JD_UNION_APP_KEY", "JD_UNION_SECRET_KEY",
    "TAOBAO_APP_KEY", "TAOBAO_APP_SECRET",
    "PDD_CLIENT_ID", "PDD_CLIENT_SECRET",
    "AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG",
    "ALIEXPRESS_OPEN_APP_KEY", "ALIEXPRESS_OPEN_APP_SECRET", "ALIEXPRESS_OPEN_ACCESS_TOKEN",
    "SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "SHOPEE_ACCESS_TOKEN", "SHOPEE_SHOP_ID",
]


def _configured_keys():
    return [k for k in KNOWN_KEYS if os.environ.get(k)]


def main():
    from shopmonitor.collectors.registry import get_adapter
    from shopmonitor.preset_data import FILE_MAP

    out = ROOT / "webdata" / "data"
    out.mkdir(parents=True, exist_ok=True)
    configured = _configured_keys()
    n_real = 0
    meta = {}
    for platform, fname in FILE_MAP.items():
        rows, src, err = [], "预置", None
        official = PLATFORM_MAP.get(platform)
        if official:
            need = _keys_for(official)
            if need and not all(os.environ.get(k) for k in need):
                err = f"未配置密钥: {', '.join(need)}（在 GitHub Secrets 添加后重跑）"
            else:
                try:
                    a = get_adapter(official)
                    if a.is_configured():
                        items = a.fetch_search(platform, limit=30) if a.supports_search else a.fetch_rank(limit=30)
                        rows = [_to_item(p, i + 1) for i, p in enumerate(items)]
                        src = f"官方API({official})"
                except Exception as e:  # noqa: BLE001
                    rows, src, err = [], "预置", f"官方API失败: {str(e)[:200]}"
        if not rows:
            rows = _preset_rows(platform)
        payload = {"items": rows, "source": src, "error": err,
                   "note": "自动数据包（每日更新，GitHub Actions 生成）"}
        (out / fname).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        meta[platform] = {"source": src, "error": err}
        n_real += 1 if src.startswith("官方") else 0
        print(f"{platform:<10} {src}  {len(rows)} 条  {err or ''}")
    # 诊断清单（配置了哪些 Key + 每平台状态），方便排错
    (ROOT / "webdata" / "meta.json").write_text(
        json.dumps({"configured_keys": configured, "platforms": meta}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"完成：{len(FILE_MAP)} 平台，真实数据 {n_real} 个，已配置 Key: {configured}")


def _keys_for(official):
    """官方适配器 -> 需要的密钥环境变量（用于提示）。"""
    return {
        "jd_union": ["JD_UNION_APP_KEY", "JD_UNION_SECRET_KEY"],
        "taobao_open": ["TAOBAO_APP_KEY", "TAOBAO_APP_SECRET"],
        "pdd_open": ["PDD_CLIENT_ID", "PDD_CLIENT_SECRET"],
        "amazon_open": ["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"],
        "aliexpress_open": ["ALIEXPRESS_OPEN_APP_KEY", "ALIEXPRESS_OPEN_APP_SECRET", "ALIEXPRESS_OPEN_ACCESS_TOKEN"],
        "shopee_open": ["SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "SHOPEE_ACCESS_TOKEN", "SHOPEE_SHOP_ID"],
    }.get(official, [])


if __name__ == "__main__":
    main()
