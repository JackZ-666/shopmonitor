"""ShopMonitor 选品监控 CLI：供 Agent 调用本地 API 出选品对比表。

用法：
    python uumit/scripts/sku_monitor.py rank --platform jd --category 手机 --limit 10
    python uumit/scripts/sku_monitor.py search --platform mock --keyword 美妆 --limit 5
    python uumit/scripts/sku_monitor.py compare --platform mock --ids demo-数码-0001,demo-数码-0002 --fmt md
    python uumit/scripts/sku_monitor.py history --platform mock --id demo-数码-0001
    python uumit/scripts/sku_monitor.py uumit-free --top 5
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def cmd_rank(base, args):
    data = _get(f"{base}/api/v1/rank/{args.platform}?category={urllib.parse.quote(args.category)}&limit={args.limit}")
    print(f"# {data['platform']} 榜单（source={data['source']} degraded={data['degraded']}）\n")
    for i in data["items"]:
        print(f"{i['rank']}. {i['title']} | ¥{i['price']} | 销量 {i['sales']} | {i['shop_name']}")


def cmd_search(base, args):
    data = _get(f"{base}/api/v1/search/{args.platform}?keyword={urllib.parse.quote(args.keyword)}&limit={args.limit}")
    print(f"# 搜索 {args.keyword}（source={data['source']}）\n")
    for i in data["items"]:
        print(f"{i['rank']}. {i['title']} | ¥{i['price']} | 销量 {i['sales']}")


def cmd_compare(base, args):
    url = f"{base}/api/v1/report/compare?platform={args.platform}&product_ids={urllib.parse.quote(args.ids)}&fmt={args.fmt}"
    with urllib.request.urlopen(url, timeout=60) as r:
        print(r.read().decode("utf-8"))


def cmd_history(base, args):
    data = _get(f"{base}/api/v1/product/{args.platform}/{args.id}/history?limit={args.limit}")
    print(f"# {args.platform} {args.id} 价格/销量历史\n")
    for rec in data["records"]:
        print(f"{rec['crawled_at']} | 价格 {rec['price']} | 销量 {rec['sales']}")


def cmd_uumit_free(base, args):
    data = _get(f"{base}/api/v1/uumit/free-data?top={args.top}")
    print(f"# UUMit 免费电商数据能力（{data['free_count']} 个）\n")
    for c in data["capabilities"]:
        print(f"- {c['title']} | api_id={c['api_id']} | direct={c['can_direct_invoke']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="sku_monitor")
    parser.add_argument("--base", default=DEFAULT_BASE)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("rank"); p.add_argument("--platform", required=True); p.add_argument("--category", default=""); p.add_argument("--limit", type=int, default=10); p.set_defaults(func=cmd_rank)
    p = sub.add_parser("search"); p.add_argument("--platform", required=True); p.add_argument("--keyword", required=True); p.add_argument("--limit", type=int, default=10); p.set_defaults(func=cmd_search)
    p = sub.add_parser("compare"); p.add_argument("--platform", required=True); p.add_argument("--ids", required=True); p.add_argument("--fmt", default="md"); p.set_defaults(func=cmd_compare)
    p = sub.add_parser("history"); p.add_argument("--platform", required=True); p.add_argument("--id", required=True); p.add_argument("--limit", type=int, default=30); p.set_defaults(func=cmd_history)
    p = sub.add_parser("uumit-free"); p.add_argument("--top", type=int, default=5); p.set_defaults(func=cmd_uumit_free)

    args = parser.parse_args()
    args.func(args.base, args)


if __name__ == "__main__":
    main()