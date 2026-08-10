# -*- coding: utf-8 -*-
"""验证京东联盟官方 API：调用商品查询接口，输出真实商品。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from shopmonitor.config import JD_UNION_APP_KEY, JD_UNION_SECRET_KEY

    if not JD_UNION_APP_KEY or not JD_UNION_SECRET_KEY:
        print("[ERR] 未配置 JD_UNION_APP_KEY / JD_UNION_SECRET_KEY（检查 配置文件.env）")
        return 1
    print(f"appkey: {JD_UNION_APP_KEY[:8]}...（已配置，secret 已配置）")
    try:
        from shopmonitor.collectors.jd_union import JDUnionAdapter

        items = JDUnionAdapter().fetch_search(keyword="手机", limit=5)
        print(f"[OK] 京东官方 API 调用成功，返回 {len(items)} 条真实商品：")
        for it in items:
            print(f"  - {it.title[:38]} | ¥{it.price} | 30天销量 {it.sales} | {it.shop_name}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[ERR] 调用失败: {type(e).__name__}: {str(e)[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())