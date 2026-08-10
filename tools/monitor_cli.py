"""ShopMonitor 定时监控 CLI。

用法：
    python tools/monitor_cli.py add --platform mock --category 数码 --top-n 5 --alias "数码榜"
    python tools/monitor_cli.py add --platform mock --mode product --product-id demo-数码-0001
    python tools/monitor_cli.py list
    python tools/monitor_cli.py run
    python tools/monitor_cli.py alerts --unread
    python tools/monitor_cli.py read
    python tools/monitor_cli.py status
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"


def _req(base: str, method: str, path: str, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def cmd_add(base, args):
    body = {
        "platform": args.platform,
        "mode": args.mode,
        "keyword": args.keyword,
        "category": args.category,
        "product_id": args.product_id,
        "alias": args.alias,
        "top_n": args.top_n,
    }
    body = {k: v for k, v in body.items() if v is not None}
    print(json.dumps(_req(base, "POST", "/api/v1/monitor/watches", body), ensure_ascii=False, indent=2))


def cmd_list(base, args):
    for w in _req(base, "GET", "/api/v1/monitor/watches")["watches"]:
        status = "开" if w["enabled"] else "停"
        print(f"#{w['id']} [{status}] {w['platform']}/{w['mode']} {w.get('keyword') or w.get('category') or w.get('product_id')} (alias={w.get('alias')}) top{ w['top_n']}")


def cmd_run(base, args):
    print(json.dumps(_req(base, "POST", "/api/v1/monitor/run"), ensure_ascii=False))


def cmd_alerts(base, args):
    path = "/api/v1/monitor/alerts?unread=true" if args.unread else "/api/v1/monitor/alerts"
    d = _req(base, "GET", path)
    print(f"未读 {d['unread']} / 总数 {d['total']}")
    for a in d["alerts"]:
        print(f"[{a['severity']}] {a['title']}: {a['message']} ({a['created_at']})")


def cmd_read(base, args):
    print(json.dumps(_req(base, "POST", "/api/v1/monitor/alerts/read", {}), ensure_ascii=False))


def cmd_status(base, args):
    print(json.dumps(_req(base, "GET", "/api/v1/monitor/status"), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="monitor_cli")
    parser.add_argument("--base", default=DEFAULT_BASE)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add"); p.add_argument("--platform", required=True); p.add_argument("--mode", default="keyword", choices=["keyword", "product"])
    p.add_argument("--keyword"); p.add_argument("--category"); p.add_argument("--product-id"); p.add_argument("--alias"); p.add_argument("--top-n", type=int, default=10); p.set_defaults(func=cmd_add)
    p = sub.add_parser("list"); p.set_defaults(func=cmd_list)
    p = sub.add_parser("run"); p.set_defaults(func=cmd_run)
    p = sub.add_parser("alerts"); p.add_argument("--unread", action="store_true"); p.set_defaults(func=cmd_alerts)
    p = sub.add_parser("read"); p.set_defaults(func=cmd_read)
    p = sub.add_parser("status"); p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args.base, args)


if __name__ == "__main__":
    main()
