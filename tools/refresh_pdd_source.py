"""刷新拼多多数据源快照（抓取 jsdelivr 上的真实商品 JSON -> 统一格式本地文件）。"""
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
SRC_URL = "https://cdn.jsdelivr.net/gh/Skeanmy/lucky-pdd@master/public/likes.json"
DST = ROOT / "data" / "拼多多榜-数据源.json"

def main():
    raw = requests.get(SRC_URL, timeout=15).json()
    goods = raw["data"]["goodsSet"]
    items = []
    for rank, (gid, g) in enumerate(goods.items(), start=1):
        price = g.get("price", 0) / 100 if isinstance(g.get("price"), (int, float)) else None
        items.append({
            "product_id": str(g.get("goodsId") or gid),
            "title": g.get("shortName") or g.get("goodsName") or "拼多多商品",
            "price": round(price, 2) if price else None,
            "shop_name": "拼多多（收藏数据源）",
            "rank": rank,
            "category": "拼多多收藏",
            "url": f"https://mobile.yangkeduo.com/goods.html?goods_id={g.get('goodsId') or gid}",
            "image": g.get("thumbUrl"),
        })
    out = {"_meta": {"source": SRC_URL, "snapshot_at": "2026-08-06", "note": "真实收藏商品，仅演示数据链路"}, "items": items}
    DST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已刷新 {DST}，商品 {len(items)} 条")

if __name__ == "__main__":
    main()
