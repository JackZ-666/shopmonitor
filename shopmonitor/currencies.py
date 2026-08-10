"""跨境结算货币与汇率：各平台结算币种 + 人民币汇率（实时获取，失败用内置快照兜底）。

口径：所有汇率 = 1 单位外币兑换多少人民币（1 USD ≈ 6.77 CNY）。
- 实时源：open.er-api.com（免费无需 key，基准 CNY）优先；失败退 frankfurter.app（ECB）；
  再失败用内置快照 DEFAULT_RATES（2026-08-09，联网后自动刷新）。
- 缓存：SHOPMONITOR_FX_TTL 秒（默认 12 小时），避免频繁请求。
"""
import os
import threading
import time
from typing import Dict, Optional, Tuple

FX_API_URLS = [
    "https://open.er-api.com/v6/latest/CNY",
    "https://api.frankfurter.app/latest?from=CNY",
]
FX_CACHE_TTL = float(os.environ.get("SHOPMONITOR_FX_TTL", "43200"))  # 12 小时

# 内置汇率快照（1 外币 = X 人民币）；联网后自动更新，仅作兜底
DEFAULT_AS_OF = "2026-08-09"
DEFAULT_RATES: Dict[str, float] = {
    "USD": 6.7650, "EUR": 7.8018, "GBP": 9.1057, "JPY": 0.0428,
    "AUD": 4.7604, "CAD": 4.8425, "MXN": 0.3942, "MYR": 1.6572,
    "THB": 0.2049, "VND": 0.0003, "PHP": 0.1108, "IDR": 0.0004,
    "SGD": 5.2895, "TWD": 0.2096, "BRL": 1.3217, "PLN": 1.8175,
    "SEK": 0.7117, "RUB": 0.0821, "TRY": 0.1422, "CLP": 0.0074,
    "COP": 0.0021, "PEN": 1.9997, "KRW": 0.0048, "CHF": 8.3518,
    "HKD": 0.8625, "INR": 0.0710, "AED": 1.8421, "SAR": 1.8040,
    "NZD": 3.9608, "EGP": 0.1359, "ZAR": 0.4171,
}

# 货币展示信息
CURRENCIES: Dict[str, dict] = {
    "CNY": {"name": "人民币", "symbol": "¥", "note": "中国大陆结算"},
    "USD": {"name": "美元", "symbol": "$", "note": "美国 Amazon / TikTok Shop 美区 / 联盟通用"},
    "EUR": {"name": "欧元", "symbol": "€", "note": "德国/法国/意大利/西班牙等 Amazon·TikTok·AliExpress 欧盟站点"},
    "GBP": {"name": "英镑", "symbol": "£", "note": "英国 Amazon / TikTok Shop 英区 / AliExpress"},
    "JPY": {"name": "日元", "symbol": "JP¥", "note": "日本 Amazon / TikTok Shop 日区"},
    "AUD": {"name": "澳元", "symbol": "A$", "note": "澳大利亚 Amazon"},
    "CAD": {"name": "加元", "symbol": "C$", "note": "加拿大 Amazon"},
    "MXN": {"name": "墨西哥比索", "symbol": "MX$", "note": "墨西哥 Amazon / TikTok Shop / Shopee"},
    "MYR": {"name": "马来西亚林吉特", "symbol": "RM", "note": "马来西亚 TikTok Shop / Shopee"},
    "THB": {"name": "泰铢", "symbol": "฿", "note": "泰国 TikTok Shop / Shopee"},
    "VND": {"name": "越南盾", "symbol": "₫", "note": "越南 TikTok Shop / Shopee"},
    "PHP": {"name": "菲律宾比索", "symbol": "₱", "note": "菲律宾 TikTok Shop / Shopee"},
    "IDR": {"name": "印尼盾", "symbol": "Rp", "note": "印尼 Shopee"},
    "SGD": {"name": "新加坡元", "symbol": "S$", "note": "新加坡 TikTok Shop / Shopee"},
    "TWD": {"name": "新台币", "symbol": "NT$", "note": "台湾 Shopee"},
    "BRL": {"name": "巴西雷亚尔", "symbol": "R$", "note": "巴西 Amazon / TikTok Shop / Shopee"},
    "PLN": {"name": "波兰兹罗提", "symbol": "zł", "note": "波兰 TikTok Shop"},
    "SEK": {"name": "瑞典克朗", "symbol": "kr", "note": "瑞典 TikTok Shop"},
    "RUB": {"name": "俄罗斯卢布", "symbol": "₽", "note": "俄罗斯 AliExpress"},
    "TRY": {"name": "土耳其里拉", "symbol": "₺", "note": "土耳其 AliExpress"},
    "KRW": {"name": "韩元", "symbol": "₩", "note": "韩国 AliExpress"},
    "CLP": {"name": "智利比索", "symbol": "CLP$", "note": "智利 Shopee"},
    "COP": {"name": "哥伦比亚比索", "symbol": "COP$", "note": "哥伦比亚 Shopee"},
    "PEN": {"name": "秘鲁索尔", "symbol": "S/", "note": "秘鲁 Shopee"},
    "CHF": {"name": "瑞士法郎", "symbol": "Fr", "note": "瑞士"},
    "HKD": {"name": "港币", "symbol": "HK$", "note": "香港"},
    "INR": {"name": "印度卢比", "symbol": "₹", "note": "印度"},
    "AED": {"name": "阿联酋迪拉姆", "symbol": "د.إ", "note": "阿联酋"},
    "SAR": {"name": "沙特里亚尔", "symbol": "﷼", "note": "沙特"},
    "NZD": {"name": "新西兰元", "symbol": "NZ$", "note": "新西兰"},
    "ZAR": {"name": "南非兰特", "symbol": "R", "note": "南非"},
}

# 各平台/渠道常用结算币种（market, currency）
PLATFORM_CURRENCIES: Dict[str, list] = {
    "amazon_open": [
        ("美国", "USD"), ("英国", "GBP"), ("德国/法国/意大利/西班牙", "EUR"),
        ("日本", "JPY"), ("加拿大", "CAD"), ("墨西哥", "MXN"), ("澳大利亚", "AUD"), ("巴西", "BRL"),
    ],
    "tiktok_shop": [
        ("美国", "USD"), ("英国", "GBP"), ("欧盟5国", "EUR"), ("波兰", "PLN"), ("瑞典", "SEK"),
        ("马来西亚", "MYR"), ("泰国", "THB"), ("越南", "VND"), ("菲律宾", "PHP"),
        ("新加坡", "SGD"), ("日本", "JPY"), ("墨西哥", "MXN"), ("巴西", "BRL"),
    ],
    "shopee_open": [
        ("马来西亚", "MYR"), ("泰国", "THB"), ("越南", "VND"), ("菲律宾", "PHP"),
        ("印尼", "IDR"), ("新加坡", "SGD"), ("台湾", "TWD"), ("巴西", "BRL"),
        ("墨西哥", "MXN"), ("智利", "CLP"), ("哥伦比亚", "COP"), ("秘鲁", "PEN"),
    ],
    "aliexpress_open": [
        ("人民币", "CNY"), ("美元", "USD"), ("欧元", "EUR"), ("英镑", "GBP"),
        ("俄罗斯", "RUB"), ("土耳其", "TRY"), ("韩国", "KRW"),
    ],
}

_cache: Dict[str, object] = {"rates": None, "source": "", "updated": "", "ts": 0.0}
_lock = threading.Lock()


def _fetch_rates() -> Tuple[Dict[str, float], str, str]:
    """实时拉取：返回 (1外币=X人民币 rates, source, updated)。"""
    import requests  # noqa: PLC0415

    for url in FX_API_URLS:
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            j = r.json()
            raw = j.get("rates") or {}
            if not raw:
                continue
            base = j.get("base_code") or j.get("base") or ""
            if base not in ("CNY", "cny"):
                continue
            rates = {}
            for code, per_cny in raw.items():
                try:
                    v = float(per_cny)
                    if v > 0:
                        rates[code.upper()] = round(1.0 / v, 4)
                except (TypeError, ValueError):
                    continue
            source = "open.er-api" if "open.er-api" in url else "frankfurter(ECB)"
            updated = (j.get("time_last_update_utc") or j.get("date") or "").replace(" 00:00:01 +0000", "")[:10]
            return rates, source, updated
        except Exception:  # noqa: BLE001
            continue
    return DEFAULT_RATES, "内置快照", DEFAULT_AS_OF


def get_rates(force: bool = False) -> dict:
    """返回 {rates, source, updated}；结果带缓存，force=True 强制刷新。"""
    now = time.time()
    with _lock:
        if not force and _cache["rates"] and now - float(_cache["ts"]) < FX_CACHE_TTL:
            return dict(_cache)
        rates, source, updated = _fetch_rates()
        _cache.update(rates=rates, source=source, updated=updated, ts=now)
        return dict(_cache)


def get_rate(code: str) -> float:
    """1 单位 code 外币 = 多少人民币；CNY=1；未知币种返回 1.0 并提示。"""
    c = (code or "CNY").upper()
    if c == "CNY":
        return 1.0
    d = get_rates()
    return float(d["rates"].get(c, 1.0))


def convert_to_cny(amount: float, code: str) -> float:
    return round(float(amount or 0) * get_rate(code), 2)


def convert_from_cny(amount: float, code: str) -> float:
    rate = get_rate(code)
    return round(float(amount or 0) / rate, 2) if rate else round(float(amount or 0), 2)


def symbol(code: str) -> str:
    c = (code or "CNY").upper()
    return CURRENCIES.get(c, {}).get("symbol", c)
