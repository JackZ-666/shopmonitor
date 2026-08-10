# -*- coding: utf-8 -*-
import subprocess, os, time, json, urllib.request
pkg = r"C:\Users\HP\Desktop\shopmonitor\dist\ShopMonitor分享版"
py = os.path.join(pkg, "runtime", "python", "python.exe")
proc = subprocess.Popen([py, "run_api.py", "--port", "8013", "--no-monitor"], cwd=pkg,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
ok = False
try:
    for i in range(40):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8013/health", timeout=3) as r:
                print("health:", r.read().decode("utf-8"))
                ok = True
                break
        except Exception:
            time.sleep(1)
    if not ok:
        print("启动超时")
finally:
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=5)
    except Exception:
        proc.kill()
        out, _ = proc.communicate()
print("---- 启动日志（GBK/UTF-8 混合解码）----")
print(out.decode("utf-8", errors="replace")[:2500])
