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


def main():
    from shopmonitor.collectors.registry import get_adapter
    from shopmonitor.preset_data import FILE_MAP

    out = ROOT / "webdata" / "data"
    out.mkdir(parents=True, exist_ok=True)
    n_real = 0
    for platform, fname in FILE_MAP.items():
        rows, src = [], "预置"
        official = PLATFORM_MAP.get(platform)
        if official:
            try:
                a = get_adapter(official)
                if a.is_configured():
                    items = a.fetch_search(platform, limit=30) if a.supports_search else a.fetch_rank(limit=30)
                    rows = [_to_item(p, i + 1) for i, p in enumerate(items)]
                    src = f"官方API({official})"
            except Exception:  # noqa: BLE001
                rows, src = [], "预置"
        if not rows:
            rows = _preset_rows(platform)
        (out / fname).write_text(
            json.dumps({"items": rows, "source": src, "note": "自动数据包（每日更新，GitHub Actions 生成）"},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        n_real += 1 if src.startswith("官方") else 0
        print(f"{platform:<10} {src}  {len(rows)} 条")
    print(f"完成：{len(FILE_MAP)} 平台，真实数据 {n_real} 个，输出 {out}")


if __name__ == "__main__":
    main()
