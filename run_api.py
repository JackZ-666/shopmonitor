"""启动 ShopMonitor API：python run_api.py [--port 8010] [--host 127.0.0.1] [--no-monitor]

端口/主机默认读取配置文件（配置文件.env 或环境变量 SHOPMONITOR_PORT / SHOPMONITOR_HOST）。
"""
import argparse

import uvicorn


def main() -> None:
    from shopmonitor.config import HOST, MONITOR_ENABLED, MONITOR_INTERVAL_SEC, PORT
    from shopmonitor.monitor import monitor

    parser = argparse.ArgumentParser(description="ShopMonitor API")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--no-monitor", action="store_true", help="不启动定时监控调度线程")
    args = parser.parse_args()
    if not args.no_monitor and MONITOR_ENABLED:
        monitor.start()
        print(f"[monitor] 定时监控调度已启动（间隔 {MONITOR_INTERVAL_SEC}s，可用 --no-monitor 关闭）")
    uvicorn.run("shopmonitor.api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
