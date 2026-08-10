"""HTTP 请求封装：统一 UA、超时、简单重试。"""
import json
import time
from pathlib import Path
from typing import Optional

import requests

from .config import REQUEST_TIMEOUT, USER_AGENT

_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
)


def fetch_text(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cookies: Optional[dict] = None,
    timeout: Optional[float] = None,
    retries: int = 2,
) -> str:
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = _session.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=timeout or REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            return r.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    raise last_err


def fetch_json(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    cookies: Optional[dict] = None,
    timeout: Optional[float] = None,
    retries: int = 2,
) -> dict:
    text = fetch_text(url, params=params, headers=headers, cookies=cookies, timeout=timeout, retries=retries)
    return json.loads(text)

def read_data_source(source: str) -> str:
    """读取数据源内容：支持 http(s) URL、file:// 路径、本地文件路径。"""
    s = (source or "").strip()
    if not s:
        raise ValueError("数据源地址为空")
    if s.startswith(("http://", "https://")):
        return fetch_text(s)
    path = s[7:] if s.startswith("file://") else s
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"数据源文件不存在: {path}")

def post_form(url: str, data: dict, timeout: Optional[float] = None) -> str:
    """POST application/x-www-form-urlencoded，返回响应文本。"""
    r = _session.post(url, data=data, timeout=timeout or REQUEST_TIMEOUT)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text


def post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: Optional[float] = None) -> str:
    """POST application/json，返回响应文本（官方 API 用，如 Amazon PA-API）。"""
    r = _session.post(
        url,
        data=json.dumps(payload, ensure_ascii=False),
        headers={"Content-Type": "application/json", **(headers or {})},
        timeout=timeout or REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text
