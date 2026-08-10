"""生成 7 平台预置数据文件（免配置模式用）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shopmonitor.preset_data import ensure_preset_files
from shopmonitor.config import BASE_DIR
n = ensure_preset_files(BASE_DIR)
print(f"已生成 {n} 个平台预置数据文件 -> {BASE_DIR / 'data' / '预置数据'}")
