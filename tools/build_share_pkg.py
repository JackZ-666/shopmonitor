# -*- coding: utf-8 -*-
"""构建 ShopMonitor 分享版（绿色便携，内置 Python，免安装免依赖）。

产物：dist/ShopMonitor分享版/（文件夹）+ ShopMonitor分享版.zip
"""
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PKG = DIST / "ShopMonitor分享版"
RUNTIME = PKG / "runtime" / "python"
PY_VERSION = "3.12.4"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"
REQ_SHARE = ROOT / "requirements-share.txt"


def log(*a):
    print("[build]", *a, flush=True)


def download(url, dest):
    log("下载", url)
    urllib.request.urlretrieve(url, dest)
    log("完成", dest, os.path.getsize(dest), "bytes")


def main():
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)
    DIST.mkdir(exist_ok=True)

    # 1) 拷贝应用文件
    for name in ("shopmonitor", "assets", "docs", "tools"):
        src = ROOT / name
        if src.exists():
            shutil.copytree(src, PKG / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("run_api.py", "requirements.txt", "配置文件-示例.env", "数据源模板.json", "README.md"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, PKG / name)
    # 预置数据（免配置模式）
    try:
        from shopmonitor.preset_data import ensure_preset_files, preset_dir
        ensure_preset_files(ROOT)
        if (ROOT / "data" / "预置数据").exists():
            shutil.copytree(ROOT / "data" / "预置数据", PKG / "data" / "预置数据",
                            dirs_exist_ok=True)
    except Exception as e:  # noqa: BLE001
        log("预置数据拷贝跳过:", e)
    log("应用文件已拷贝")

    # 2) 内置 Python
    RUNTIME.mkdir(parents=True)
    tmp = DIST / "pyembed.zip"
    download(PY_URL, tmp)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(RUNTIME)
    tmp.unlink(missing_ok=True)
    # 启用 site-packages
    pth = next(RUNTIME.glob("python*._pth"))
    pth_text = pth.read_text(encoding="utf-8").replace("#import site", "import site")
    if "..\\.." not in pth_text:
        pth_text += "\\r\\n..\\..\\r\\n"
    pth.write_text(pth_text, encoding="utf-8")
    log("内置 Python 就绪:", RUNTIME)

    # 3) pip + 依赖
    getpip = DIST / "get-pip.py"
    download(GETPIP_URL, getpip)
    py = RUNTIME / "python.exe"
    subprocess.run([str(py), str(getpip), "--no-warn-script-location"], check=True)
    getpip.unlink(missing_ok=True)
    subprocess.run([str(py), "-m", "pip", "install", "--no-warn-script-location", "-r", str(REQ_SHARE)], check=True)
    log("依赖安装完成")

    # 4) 启动/停止/快捷方式脚本
    (PKG / "启动-选品监控.bat").write_text(
        '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\ntitle ShopMonitor 选品监控\r\n'
        'if not exist "runtime\\python\\python.exe" (echo [错误] 未找到内置 Python，请重新解压完整包。 & pause & exit /b 1)\r\n'
        '"runtime\\python\\python.exe" tools\\launcher.py start\r\npause\r\n',
        encoding="utf-8")
    (PKG / "停止服务.bat").write_text(
        '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n'
        '"runtime\\python\\python.exe" tools\\launcher.py stop\r\npause\r\n',
        encoding="utf-8")
    (PKG / "创建桌面快捷方式.bat").write_text(
        '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n'
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath(\'Desktop\'); '
        '$s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+\'\\ShopMonitor 选品监控.lnk\'); '
        '$s.TargetPath=\'%~dp0启动-选品监控.bat\'; $s.WorkingDirectory=\'%~dp0\'; '
        '$s.IconLocation=\'%~dp0assets\\logo.ico,0\'; $s.Description=\'ShopMonitor 选品监控面板\'; $s.Save()"\r\n'
        'echo 已创建桌面快捷方式「ShopMonitor 选品监控」，双击即可启动。\r\npause\r\n',
        encoding="utf-8")

    # 5) logo.ico
    try:
        from PIL import Image
        img = Image.open(str(ROOT / "assets" / "logo.png")).convert("RGBA")
        img.save(str(PKG / "assets" / "logo.ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
        log("logo.ico 已生成")
    except Exception as e:  # noqa: BLE001
        log("logo.ico 生成跳过:", e)

    # 6) 使用说明
    (PKG / "使用说明.txt").write_text(
        "【ShopMonitor 选品监控面板 · 绿色便携版】\r\n"
        "\r\n"
        "一、运行\r\n"
        "  1. 把整个「ShopMonitor分享版」文件夹（或解压 zip）放到任意位置（建议 D 盘，路径别带中文）。\r\n"
        "  2. 双击「启动-选品监控.bat」，等 1-3 秒自动打开浏览器 http://127.0.0.1:8010/ 。\r\n"
        "     （内置了 Python 和全部依赖，不需要装任何东西）\r\n"
        "  3. 用完点「停止服务.bat」或直接关浏览器即可（后台服务会继续，随时可再开）。\r\n"
        "\r\n"
        "二、想要桌面快捷方式\r\n"
        "  双击「创建桌面快捷方式.bat」→ 桌面出现「ShopMonitor 选品监控」图标，以后双击图标直接启动。\r\n"
        "\r\n"
        "三、数据说明\r\n"
        "  - 首次打开即有 7 大平台数据（预置样例），可跑通全部功能。\r\n"
        "  - 一键启用预置数据：接口文档 → 配置中心 → 「一键启用预置数据」。\r\n"
        "  - 想点亮真实数据：在「接口文档 → 配置中心」填平台 API 凭证，或把榜单 JSON 放 data 目录。\r\n"
        "  - 你的监控数据（关注/告警/选品库/快照）都保存在本文件夹 data 目录，重装系统前先备份。\r\n"
        "\r\n"
        "四、接入数据服务（可选，让数据每日自动更新）\r\n"
        "  1. 打开「接口文档 → 配置中心」。\r\n"
        "  2. 在「数据包 base 地址」框填入服务商给你的地址（如 https://xxx.github.io/仓库名）。\r\n"
        "  3. 点「一键填数据包」→ 点「保存配置」→ 等待自动重启。\r\n"
        "  4. 之后 7 大平台数据由服务商每日自动更新，你无需任何操作。\r\n"
        "\r\n"
        "五、常见问题\r\n"
        "  - 端口被占用：改 配置文件.env 里的 SHOPMONITOR_PORT=8010 换一个端口。\r\n"
        "  - 杀毒软件误报：bat 启动方式为常见行为，可加信任；代码全部开源无后门。\r\n"
        "\r\n"
        "六、技术栈\r\n"
        "  Python + FastAPI + SQLite，单机本地运行，数据不出本机。\r\n",
        encoding="utf-8")

    # 7) 压缩
    zip_path = DIST / "ShopMonitor分享版.zip"
    if zip_path.exists():
        zip_path.unlink()
    log("压缩中…")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in PKG.rglob("*"):
            if "__pycache__" in str(f) or f.suffix == ".pyc":
                continue
            z.write(f, f.relative_to(PKG))
    log("完成！")
    log("文件夹:", PKG)
    log("压缩包:", zip_path, round(os.path.getsize(zip_path) / 1024 / 1024, 1), "MB")


if __name__ == "__main__":
    main()
