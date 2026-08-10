"""运维/配置层测试：.env 加载、启动器自检。"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dotenv_inline_comment():
    from shopmonitor.config import _load_dotenv

    key = "SHOPMONITOR_TEST_INLINE_UNIQUE"
    key2 = "SHOPMONITOR_TEST_INLINE_URL"
    os.environ.pop(key, None)
    os.environ.pop(key2, None)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cfg.env"
        p.write_text(
            f"{key}=8010 # 面板端口\n{key2}=https://x.com/a # webhook\n", encoding="utf-8"
        )
        _load_dotenv(p)
        assert os.environ.get(key) == "8010"
        assert os.environ.get(key2) == "https://x.com/a"
        os.environ.pop(key, None)
        os.environ.pop(key2, None)


def test_dotenv_loader():
    from shopmonitor.config import _load_dotenv

    key = "SHOPMONITOR_TEST_DOTENV_UNIQUE"
    os.environ.pop(key, None)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cfg.env"
        p.write_text(
            f"# 注释\n{key}=hello world\nALREADY_SET=ignored\n",
            encoding="utf-8",
        )
        os.environ["ALREADY_SET"] = "keep"
        _load_dotenv(p)
        assert os.environ.get(key) == "hello world"
        assert os.environ.get("ALREADY_SET") == "keep"
        os.environ.pop(key, None)


def test_config_file_example_exists():
    assert (ROOT / "配置文件-示例.env").exists()
    assert (ROOT / "启动.bat").exists()
    assert (ROOT / "tools" / "launcher.py").exists()


def test_launcher_check():
    r = subprocess.run(
        [sys.executable, "tools/launcher.py", "check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert r.returncode == 0
    assert "自检" in r.stdout

def test_read_data_source_local_file(tmp_path):
    from shopmonitor.http_utils import read_data_source

    f = tmp_path / "data.json"
    f.write_text('{"items": []}', encoding="utf-8")
    assert read_data_source(str(f)) == '{"items": []}'
    assert read_data_source("file://" + str(f)) == '{"items": []}'
