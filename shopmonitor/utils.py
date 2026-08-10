"""通用小工具：数值/文本清洗。"""
import re
from typing import Optional


def to_float(value) -> Optional[float]:
    """从 '¥1,299.00' / '12.99' 等文本里提取第一个浮点数。"""
    if value is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group()) if m else None


def to_int(value) -> Optional[int]:
    """从 '已拼 1.2万件' / '10万+' 等文本里提取整数（万换算）。"""
    if value is None:
        return None
    s = str(value).replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([万亿]?)", s)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        num *= 10000
    elif unit == "亿":
        num *= 100000000
    return int(num)


def clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()