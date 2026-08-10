"""抖音电商适配器：榜单接口需签名，默认走自定义 JSON 数据源（环境变量）。

接入方式：配置 SHOPMONITOR_DOUYIN_RANK_URL=<返回商品列表 JSON 的接口地址>，
JSON 结构同 pdd（数组或 {"items":[...]}），字段：product_id/title/price/sales/shop_name/rank/url。
"""
import json
from typing import List, Optional

from ..config import DOUYIN_RANK_URL
from ..http_utils import read_data_source, fetch_text
from ..models import Product
from .base import CollectorError, PlatformAdapter
from .env_json import parse_items_json


class DouyinAdapter(PlatformAdapter):
    platform = "douyin"
    display_name = "抖音电商"
    regions = "国内"
    availability = "需配置数据源（默认走自定义 JSON 接口）"
    supports_search = False
    default_category = "热卖榜"

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        if not DOUYIN_RANK_URL:
            raise CollectorError(
                "抖音电商热榜接口需要 a_bogus 签名，当前无法公开直采。"
                "请配置环境变量 SHOPMONITOR_DOUYIN_RANK_URL 指向返回商品列表 JSON 的接口，"
                "或接入巨量/电商开放平台官方接口（见 docs/PLATFORM_STATUS.md）。"
            )
        raw = read_data_source(DOUYIN_RANK_URL)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise CollectorError(f"抖音自定义数据源不是合法 JSON: {e}") from e
        return parse_items_json(payload, platform=self.platform, category=category or "热卖榜", limit=limit)