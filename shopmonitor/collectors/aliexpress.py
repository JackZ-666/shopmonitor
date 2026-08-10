"""AliExpress 适配器：反爬较强，默认走自定义 JSON 数据源。"""
import json
from typing import List, Optional

from ..config import ALIEXPRESS_RANK_URL
from ..http_utils import read_data_source, fetch_text
from ..models import Product
from .base import CollectorError, PlatformAdapter
from .env_json import parse_items_json


class AliExpressAdapter(PlatformAdapter):
    platform = "aliexpress"
    display_name = "AliExpress（速卖通）"
    regions = "跨境"
    availability = "需配置数据源（默认走自定义 JSON 接口）"
    supports_search = False
    default_category = "热卖榜"

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        if not ALIEXPRESS_RANK_URL:
            raise CollectorError(
                "AliExpress 反爬较强，请配置环境变量 SHOPMONITOR_ALIEXPRESS_RANK_URL "
                "指向返回商品列表 JSON 的接口（可接官方开放平台/第三方数据服务），见 docs/PLATFORM_STATUS.md。"
            )
        raw = read_data_source(ALIEXPRESS_RANK_URL)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise CollectorError(f"AliExpress 自定义数据源不是合法 JSON: {e}") from e
        return parse_items_json(payload, platform=self.platform, category=category or "热卖榜", limit=limit)