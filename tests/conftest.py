"""pytest 全局配置：隔离数据目录、关闭限流、UTF-8 输出。"""
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

os.environ["SHOPMONITOR_DATA_DIR"] = tempfile.mkdtemp(prefix="shopmonitor_test_")
os.environ["SHOPMONITOR_RATE_LIMIT"] = "0"
os.environ["SHOPMONITOR_ALLOW_MOCK"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"