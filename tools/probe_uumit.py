"""UUMit 免费数据源状态：账户 + 免费电商数据能力 + 一次免费调用示例。

用法：
    python tools/probe_uumit.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopmonitor import uumit_feed  # noqa: E402


def main() -> None:
    print("=== UUMit 账户 ===")
    try:
        acc = uumit_feed.account_status()
        print(f"UT 余额={acc['ut_balance']}  可用={acc['ut_available']}  可提现={acc['ut_withdrawable']}")
    except uumit_feed.UumitError as e:
        print("账户查询失败:", e)

    print("\n=== 免费电商数据能力（price_ut=0） ===")
    try:
        caps = uumit_feed.discover_free_capabilities(top=8)
        print(f"发现 {len(caps)} 个免费数据能力:")
        for c in caps:
            print(f"  - {c['title']} | api_id={c['api_id']} | direct={c['can_direct_invoke']}")
    except uumit_feed.UumitError as e:
        print("发现失败:", e)
        return

    if caps:
        api_id = caps[0]["api_id"]
        print(f"\n=== 免费调用示例: {caps[0]['title']} ===")
        detail = uumit_feed.data_api_detail(api_id)
        print("接口说明:", (detail.get("description") or "")[:80])
        try:
            res = uumit_feed.call_free_data_api(api_id, {"grain": "month", "dateFrom": "2024-01-01", "dateTo": "2024-03-31"})
            print(f"状态={res['status']} 计费={res.get('charged_ut')} UT 耗时={res.get('latency_ms')}ms")
            items = (res.get("result") or {}).get("data", {}).get("items", [])
            for it in items[:5]:
                print(f"  {it.get('period')}: 订单 {it.get('order_count')} 成交额 {it.get('total_amount')}")
        except uumit_feed.UumitError as e:
            print("调用失败:", e)


if __name__ == "__main__":
    main()