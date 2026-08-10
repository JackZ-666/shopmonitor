"""真实平台连通性探测：逐个尝试各真实适配器（每条 3 个商品），输出 ✅/❌。

用法：
    python tools/probe_platforms.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopmonitor.collectors.registry import get_adapter, list_platforms  # noqa: E402


def main() -> None:
    print("=== 真实平台连通性探测 ===")
    for info in list_platforms():
        plat = info["platform"]
        if plat == "mock":
            continue
        adapter = get_adapter(plat)
        try:
            t0 = time.time()
            items = adapter.fetch_rank(category=None, limit=3)
            dt = time.time() - t0
            sample = items[0].title if items else ""
            print(f"[OK] {plat:10s} {adapter.display_name:16s} {len(items)} 条 | 示例: {sample[:40]} | {dt:.1f}s")
        except Exception as e:  # noqa: BLE001
            print(f"[XX] {plat:10s} {adapter.display_name:16s} {str(e)[:140]}")
        time.sleep(1.0)
    print("=== 探测完成 ===")


if __name__ == "__main__":
    main()