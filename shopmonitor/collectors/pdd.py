"""拼多多适配器：反爬签名较强，默认走自定义 JSON 数据源（环境变量）。

接入方式（任选其一，无需改代码）：
- 配置 SHOPMONITOR_PDD_RANK_URL=<返回商品列表 JSON 的接口地址>
- 或接入拼多多开放平台官方接口后，把响应转成下面 JSON 结构即可。

JSON 结构（数组或 {"items": [...]}）：
[{"product_id":"id","title":"标题","price":12.9,"sales":1000,
  "sales_text":"已拼1千件","shop_name":"店铺","rank":1,"url":"链接"}]
"""
import json
from typing import List, Optional

from ..config import PDD_RANK_URL
from ..http_utils import read_data_source, fetch_text
from ..models import Product
from ..utils import to_float, to_int
from .base import CollectorError, PlatformAdapter
from .env_json import parse_items_json


class PDDAdapter(PlatformAdapter):
    platform = "pdd"
    display_name = "拼多多"
    regions = "国内"
    availability = "需配置数据源（默认走自定义 JSON 接口）"
    supports_search = False
    default_category = "热卖榜"

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        if not PDD_RANK_URL:
            raise CollectorError(
                "拼多多接口需要 anti-content 签名，当前无法公开直采。"
                "请配置环境变量 SHOPMONITOR_PDD_RANK_URL 指向返回商品列表 JSON 的接口，"
                "或接入拼多多开放平台官方接口（见 docs/PLATFORM_STATUS.md）。"
            )
        raw = read_data_source(PDD_RANK_URL)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise CollectorError(f"拼多多自定义数据源不是合法 JSON: {e}") from e
        return parse_items_json(payload, platform=self.platform, category=category or "热卖榜", limit=limit)