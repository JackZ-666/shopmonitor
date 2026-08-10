"""ShopMonitor 一键启动器：启动/停止/状态/自检 + 中文管理菜单。

用法：
    python tools/launcher.py start [--no-browser]   # 启动服务
    python tools/launcher.py stop                   # 停止服务
    python tools/launcher.py status                 # 查看状态
    python tools/launcher.py check                  # 环境自检
    python tools/launcher.py menu                   # 中文管理菜单

注意：内部 HTTP 调用统一使用英文路径，避免中文 URL 编码问题；展示给用户时用中文。
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "data" / "server.pid"


def _port():
    sys.path.insert(0, str(ROOT))
    from shopmonitor.config import PORT

    return PORT


def _base():
    return f"http://127.0.0.1:{_port()}"


def _alive() -> bool:
    try:
        with urllib.request.urlopen(_base() + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _read_pid():
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _find_pid_by_port(port: int):
    """Windows：通过 netstat -ano 反查监听端口的 PID。"""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10
        ).stdout
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    return int(parts[-1])
    except Exception:
        pass
    return None


def cmd_start(args) -> None:
    if _alive():
        print(f"[OK] 服务已在运行：{_base()}/docs")
        return
    proc = subprocess.Popen(
        [sys.executable, "run_api.py", "--port", str(_port())],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _write_pid(proc.pid)
    for _ in range(40):
        if _alive():
            break
        time.sleep(0.5)
    if not _alive():
        print("[ERROR] 启动失败，请运行 python tools/launcher.py check 自检")
        return
    print(f"[OK] 服务已启动：{_base()}/docs")
    print(f"[OK] PID={proc.pid}，定时监控调度已随服务启动")
    if not args.no_browser:
        webbrowser.open(_base() + "/docs")


def cmd_stop(_args) -> None:
    pid = _read_pid() or _find_pid_by_port(_port())
    if pid:
        for sig in (signal.SIGTERM, 9):
            try:
                os.kill(pid, sig)
                for _ in range(20):
                    if not _alive():
                        break
                    time.sleep(0.3)
            except OSError:
                pass
            if not _alive():
                break
    if _alive():
        print("[WARN] 未能停止，请手动结束 run_api.py 进程")
    else:
        print("[OK] 服务已停止")


def cmd_status(_args) -> None:
    if not _alive():
        print("[STOP] 服务未运行")
        return
    try:
        st = _api("GET", "/api/v1/monitor/status")
        al = _api("GET", "/api/v1/monitor/alerts?limit=5")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 状态读取失败: {e}")
        return
    print(f"[RUN] {_base()}/docs")
    print(f"      调度线程: {'运行中' if st['scheduler_running'] else '未运行'}  轮询间隔: {st['interval_sec']}s")
    print(f"      关注项: {st['watch_count']}  未读告警: {st['unread_alerts']}")
    print(f"      最近巡检: {st.get('last_summary')}")
    for a in al["alerts"][:5]:
        print(f"      [{a['severity']}] {a['title']}: {a['message']}")


def cmd_check(_args) -> None:
    ok = True
    try:
        import fastapi, requests, bs4, openpyxl  # noqa: F401
        print("[OK] Python 依赖已安装")
    except ImportError as e:
        ok = False
        print(f"[ERR] 缺少依赖: {e}，请运行 安装依赖.bat 或 pip install -r requirements.txt")
    import shutil

    if shutil.which("python"):
        print("[OK] python 可用")
    else:
        ok = False
        print("[ERR] 未找到 python")
    skill = Path.home() / ".codex" / "skills" / "uumit-agent" / "scripts" / "rest_request.js"
    print("[OK] UUMit 技能已接入" if skill.exists() else "[WARN] 未找到 uumit-agent 技能（UUMit 免费数据不可用）")
    print("[OK] 环境自检通过，可运行 启动.bat" if ok else "[ERR] 环境自检未通过")


def cmd_menu(_args) -> None:
    print("===== ShopMonitor 管理菜单 =====")
    while True:
        print("\n1. 启动服务    2. 停止服务    3. 查看状态")
        print("4. 添加监控关注  5. 立即巡检   6. 查看告警")
        print("7. 打开接口文档  8. 退出")
        choice = input("请输入编号回车：").strip()
        if choice == "1":
            cmd_start(argparse.Namespace(no_browser=False))
        elif choice == "2":
            cmd_stop(None)
        elif choice == "3":
            cmd_status(None)
        elif choice == "4":
            platform = input("平台（jd/pdd/douyin/taobao/shopee/amazon/aliexpress/mock）：").strip() or "mock"
            keyword = input("关键词/类目（如 数码）：").strip() or "数码"
            top_n = input("盯前 N 名（默认10）：").strip() or "10"
            body = {"platform": platform, "mode": "keyword", "category": keyword, "top_n": int(top_n)}
            _api("POST", "/api/v1/monitor/watches", body)
            print(f"[OK] 已添加关注：{platform}/{keyword} Top{top_n}")
        elif choice == "5":
            print(_api("POST", "/api/v1/monitor/run"))
        elif choice == "6":
            al = _api("GET", "/api/v1/monitor/alerts?limit=20")
            print(f"未读 {al['unread']} / 总数 {al['total']}")
            for a in al["alerts"]:
                print(f"  [{a['severity']}] {a['title']}: {a['message']} ({a['created_at']})")
        elif choice == "7":
            webbrowser.open(_base() + "/docs")
        elif choice == "8":
            print("再见")
            break
        else:
            print("无效输入")


def _api(method: str, path: str, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        _base() + path, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(prog="launcher")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--no-browser", action="store_true"); p.set_defaults(func=cmd_start)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("menu").set_defaults(func=cmd_menu)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
