"""数据模型（Pydantic）。"""
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Product(BaseModel):
    platform: str
    product_id: str
    title: str
    price: Optional[float] = None
    original_price: Optional[float] = None
    sales: Optional[int] = None
    sales_text: Optional[str] = None
    shop_name: Optional[str] = None
    shop_rating: Optional[float] = None      # 店铺评分
    brand: Optional[str] = None              # 品牌
    rating: Optional[float] = None           # 商品评分（0-5）
    review_count: Optional[int] = None       # 评论数
    stock_status: Optional[str] = None       # 现货 / 缺货 / 预售 / 未知
    promo_text: Optional[str] = None         # 促销信息（秒杀/优惠券/折扣）
    is_promo: Optional[bool] = None          # 是否有促销
    rank: Optional[int] = None               # 榜单/搜索位次
    category: Optional[str] = None
    url: Optional[str] = None
    image: Optional[str] = None
    crawled_at: str = Field(default_factory=_now)


class RankResponse(BaseModel):
    platform: str
    category: Optional[str] = None
    source: str = "live"  # live | cache | mock
    degraded: bool = False
    generated_at: str = Field(default_factory=_now)
    items: List[Product] = Field(default_factory=list)


class SearchResponse(RankResponse):
    keyword: Optional[str] = None


class HistoryPoint(BaseModel):
    price: Optional[float] = None
    sales: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    crawled_at: str


class HistoryResponse(BaseModel):
    platform: str
    product_id: str
    records: List[HistoryPoint] = Field(default_factory=list)


class ChangeInfo(BaseModel):
    """价格/销量/评价 涨跌分析（取最近两次抓取对比）。"""
    platform: str
    product_id: str
    price_now: Optional[float] = None
    price_before: Optional[float] = None
    price_change: Optional[float] = None
    price_change_pct: Optional[float] = None
    sales_now: Optional[int] = None
    sales_before: Optional[int] = None
    sales_change: Optional[int] = None
    sales_change_pct: Optional[float] = None
    rating_now: Optional[float] = None
    review_change: Optional[int] = None
    direction: str = "flat"  # up / down / flat
    note: str = ""


class CompareRow(BaseModel):
    platform: str
    product_id: str
    title: str
    price: Optional[float] = None
    sales: Optional[int] = None
    shop_name: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    stock_status: Optional[str] = None
    promo_text: Optional[str] = None
    rank: Optional[int] = None
    url: Optional[str] = None
    estimated_profit: Optional[float] = None   # 预估毛利（售价×…−成本−运费，见 insights.estimate_item_profit）
    estimated_margin: Optional[float] = None   # 预估毛利率（%）
    crawled_at: str = ""


class WatchCreate(BaseModel):
    """新增监控关注项。mode=keyword：盯榜单/搜索前 top_n；mode=product：盯单个商品。"""
    platform: str = Field(..., description="平台：jd/pdd/douyin/taobao/shopee/amazon/aliexpress/mock")
    mode: str = Field("keyword", pattern="^(keyword|product)$")
    keyword: Optional[str] = Field(None, description="关键词/类目（keyword 模式）")
    category: Optional[str] = Field(None, description="榜单类目（keyword 模式，优先于 keyword）")
    product_id: Optional[str] = Field(None, description="商品 ID（product 模式）")
    alias: Optional[str] = Field(None, description="备注名")
    top_n: int = Field(10, ge=1, le=100, description="盯前 N 名")
    target_price: Optional[float] = Field(None, description="目标价：现价跌破时自动告警（Keepa 风格）")
    enabled: bool = True
