"""官方开放平台适配器：抖店 / 淘宝 / 拼多多 / 1688 / 快手。

设计原则（与全站一致）：
- 凭证没配齐 -> 抛 CollectorError("未配置…")，上层框架自动降级为演示数据（degraded=true），流程不中断。
- 凭证配齐 -> 按各平台官方文档生成签名/Token，发起真实请求，把官方响应解析成统一 Product。
- 官方返回"未开通/无权限/欠费/风控/签名错误" -> 同样映射为 CollectorError（自动降级，不崩服务）。
- 所有解析函数都是纯函数，可用固定样例做单测，不依赖真联网。

签名规范（按官方文档，均已备注来源）：
- 抖店: md5(app_secret + app_key+值 + method+值 + param_json+值 + timestamp+值 + v+值 + app_secret)，param_json 内部 key 需升序
- 淘宝: md5(secret + 参数按 ASCII 升序 key+value 拼接 + secret) 大写（同京东 TOP 规范）
- 拼多多: md5(client_secret + 公共+业务参数按 ASCII 升序 key+value 拼接 + client_secret) 大写
- 1688: base64(HMAC-SHA1(app_secret, 参数按 ASCII 升序 key+value 拼接))，param2 风格，带 access_token
- 快手: md5(app_secret + 公共+业务参数按 ASCII 升序 key+value 拼接 + app_secret) 大写
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime
from typing import List, Optional, Tuple

from ..config import (
    ALIBABA_APP_KEY,
    ALIBABA_APP_SECRET,
    DOUYIN_MALL_APP_ID,
    DOUYIN_MALL_SECRET,
    KUAISHOU_APP_KEY,
    KUAISHOU_APP_SECRET,
    PDD_CLIENT_ID,
    PDD_CLIENT_SECRET,
    TAOBAO_APP_KEY,
    TAOBAO_APP_SECRET,
)
from ..http_utils import fetch_text, post_form
from ..models import Product
from ..utils import clean_text, to_float, to_int
from .base import CollectorError, PlatformAdapter


# ---------------------------------------------------------------------------
# 通用签名 / 时间戳工具（纯函数，便于单测）
# ---------------------------------------------------------------------------
def md5_sign(params: dict, secret: str, *, skip: Tuple[str, ...] = ()) -> str:
    """通用 MD5 签名：md5(secret + 参数升序 key+value + secret) 大写。

    - 只剔除 sign / _aop_signature （自定义 skip 可额外剔除）；sign_method 等公共参数参与签名
    - 空值参数不参与（淘宝 TOP 规范）
    """
    items = sorted(
        (k, str(v)) for k, v in params.items()
        if k not in ("sign", "_aop_signature", *skip) and v not in (None, "")
    )
    raw = "".join(f"{k}{v}" for k, v in items)
    return hashlib.md5((secret + raw + secret).encode("utf-8")).hexdigest().upper()


def hmac_sha1_base64(params: dict, secret: str) -> str:
    """1688 param2 风格签名：base64(HMAC-SHA1(app_secret, 参数升序 key+value 拼接))。"""
    items = sorted((k, str(v)) for k, v in params.items() if k not in ("_aop_signature",) and v not in (None, ""))
    raw = "".join(f"{k}{v}" for k, v in items)
    digest = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def sorted_json(obj: dict) -> str:
    """生成 key 升序、无空格的 JSON 字符串（抖店 param_json 要求）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _tb_timestamp() -> str:
    """淘宝时间戳：yyyy-MM-dd HH:mm:ss（GMT+8）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------
class OfficialAdapter(PlatformAdapter):
    """官方开放平台适配器基类。

    - credential_keys: 必填凭证的环境变量名（如 DOUYIN_MALL_APP_ID / DOUYIN_MALL_SECRET）
    - _get_credentials(): 校验并返回 (key, secret) 元组
    - 子类只需实现 fetch_rank / fetch_search / _parse_items 与请求组装
    """

    credential_keys: Tuple[str, ...] = ()
    rate_limit_sec = 1.0

    def is_configured(self) -> bool:
        return all(os.environ.get(k) for k in self.credential_keys)

    def _get_credentials(self) -> Tuple[str, str]:
        missing = [k for k in self.credential_keys if not os.environ.get(k)]
        if missing:
            raise CollectorError(
                f"未配置 {self.display_name} 凭证：{', '.join(missing)}。"
                "请在「接口文档 → 配置中心 → 官方开放平台凭证」填写后再试。"
            )
        return tuple(os.environ.get(k) for k in self.credential_keys)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 1) 抖店（抖音商城）—— op.jinritemai.com 开放平台
# ---------------------------------------------------------------------------
class DouyinMallAdapter(OfficialAdapter):
    """抖店官方 API：商品列表（product.list）。

    签名（官方 gen-sign 文档）：
    - param_json 内部 key 升序、无空格
    - sign = md5(app_secret + app_key+值 + method+值 + param_json+值 + timestamp+值 + v+值 + app_secret) 大写
    - 参与签名的公共参数顺序固定：app_key, method, param_json, timestamp, v（access_token 不参与）
    """

    platform = "douyin_mall"
    display_name = "抖店（官方 API）"
    regions = "国内"
    availability = "官方 API（已配置 AppID/Secret）"
    supports_search = False
    default_category = "全部商品"
    credential_keys = ("DOUYIN_MALL_APP_ID", "DOUYIN_MALL_SECRET")
    BASE = "https://openapi-fxg.jinritemai.com"

    def rank_categories(self) -> List[str]:
        return ["全部商品", "服饰内衣", "美妆护肤", "食品饮料", "数码家电", "母婴玩具", "家居家装"]

    def _douyin_sign(self, app_key: str, secret: str, method: str, param_json: str, timestamp: str, v: str) -> str:
        raw = f"{app_key}{method}{param_json}{timestamp}{v}"
        return hashlib.md5((secret + raw + secret).encode("utf-8")).hexdigest().upper()

    def _list_products(self, page: int, page_size: int) -> List[Product]:
        app_key, secret = self._get_credentials()
        method = "product.list"
        param_json = sorted_json({"page": page, "page_size": page_size, "status": 0})  # 0=上架
        timestamp = str(int(datetime.now().timestamp()))
        v = "2"
        params = {
            "app_key": app_key,
            "method": method,
            "param_json": param_json,
            "timestamp": timestamp,
            "v": v,
        }
        token = os.environ.get("DOUYIN_MALL_ACCESS_TOKEN", "")
        if token:
            params["access_token"] = token
        params["sign"] = self._douyin_sign(app_key, secret, method, param_json, timestamp, v)
        text = fetch_text(self.BASE, params=params)
        resp = _loads(text, self.display_name)
        if resp.get("err_no") not in (0, None, "0"):
            raise CollectorError(f"抖店错误 err_no={resp.get('err_no')}: {resp.get('err_msg') or resp.get('message')}")
        data = resp.get("data") or {}
        rows = data.get("data") if isinstance(data, dict) else data
        if isinstance(rows, dict):
            rows = rows.get("list") or rows.get("products") or []
        return self._parse_items(rows or [], "全部商品", 100)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        # 抖店商品列表不支持类目筛选（返回本店全部在售），类目仅作展示
        items = self._list_products(1, min(limit, 100))
        return items[:limit]

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        raise CollectorError("抖店官方接口暂无商品关键词搜索权限，请用榜单/商品列表，或接入巨量电商选品 API")

    def fetch_product(self, product_id: str) -> Product:
        app_key, secret = self._get_credentials()
        method = "product.detail"
        param_json = sorted_json({"product_id": str(product_id)})
        timestamp = str(int(datetime.now().timestamp()))
        v = "2"
        params = {"app_key": app_key, "method": method, "param_json": param_json, "timestamp": timestamp, "v": v}
        token = os.environ.get("DOUYIN_MALL_ACCESS_TOKEN", "")
        if token:
            params["access_token"] = token
        params["sign"] = self._douyin_sign(app_key, secret, method, param_json, timestamp, v)
        resp = _loads(fetch_text(self.BASE, params=params), self.display_name)
        if resp.get("err_no") not in (0, None, "0"):
            raise CollectorError(f"抖店错误 err_no={resp.get('err_no')}: {resp.get('err_msg')}")
        data = resp.get("data") or {}
        items = self._parse_items([data] if isinstance(data, dict) else [], "商品", 1)
        for it in items:
            if str(it.product_id) == str(product_id):
                return it
        raise CollectorError(f"抖店未找到商品 {product_id}")

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("product_id") or g.get("id") or "")
            if not pid:
                continue
            price = _fen2yuan(to_float(g.get("price")))  # 抖店金额单位：分
            imgs = g.get("img") or g.get("images") or []
            _st = g.get("status")
            status = str(_st) if _st is not None else ""
            stock = "现货" if status == "0" else ("缺货" if status == "2" else None)
            products.append(
                Product(
                    platform="douyin_mall",
                    product_id=pid,
                    title=clean_text(g.get("name") or g.get("title") or "未命名商品"),
                    price=price,
                    original_price=_fen2yuan(to_float(g.get("market_price"))),
                    sales=to_int(g.get("sales") or g.get("sale_count")),
                    sales_text=f"月销 {g.get('sales')}" if g.get("sales") is not None else None,
                    shop_name=clean_text(g.get("shop_name") or g.get("shop") or "抖店商家"),
                    brand=clean_text(g.get("brand")),
                    stock_status=stock,
                    rank=rank,
                    category=clean_text(g.get("first_cid_name") or g.get("category_name")) or category,
                    url=f"https://haohuo.jinritemai.com/views/product/item2?id={pid}",
                    image=imgs[0] if isinstance(imgs, list) and imgs else (imgs if isinstance(imgs, str) else None),
                )
            )
        if not products:
            raise CollectorError("抖店返回为空（检查 AppID/Secret 权限：需开通 product.list 与商品读权限）")
        return products


# ---------------------------------------------------------------------------
# 2) 淘宝开放平台 —— taobao.tbk.dg.material.optional（淘宝客物料搜索，选品常用）
# ---------------------------------------------------------------------------
class TaobaoOpenAdapter(OfficialAdapter):
    """淘宝开放平台官方 API：淘宝客物料搜索（选品）。

    签名（TOP 规范）：sign = md5(secret + 参数按 ASCII 升序 key+value + secret) 大写。
    提示：taobao.tbk.dg.material.optional 需开通淘宝客权限；adzone_id 选填（部分账号必填）。
    """

    platform = "taobao_open"
    display_name = "淘宝（官方 API）"
    regions = "国内"
    availability = "官方 API（已配置 AppKey/Secret）"
    supports_search = True
    default_category = "热销商品"
    credential_keys = ("TAOBAO_APP_KEY", "TAOBAO_APP_SECRET")
    BASE = "https://eco.taobao.com/router/rest"

    def rank_categories(self) -> List[str]:
        return ["热销商品", "女装", "美妆", "数码", "家居", "食品", "母婴"]

    def _call_material(self, keyword: str, page: int, page_size: int) -> List[Product]:
        app_key, secret = self._get_credentials()
        params = {
            "method": "taobao.tbk.dg.material.optional",
            "app_key": app_key,
            "timestamp": _tb_timestamp(),
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
            "q": keyword,
            "page_no": page,
            "page_size": page_size,
            "sort": "total_sales_des",  # 近30天销量降序
            "need_free_shipment": "true",
        }
        adzone = os.environ.get("TAOBAO_ADZONE_ID", "")
        if adzone:
            params["adzone_id"] = adzone
        params["sign"] = md5_sign(params, secret)
        resp = _loads(fetch_text(self.BASE, params=params), self.display_name)
        _check_taobao_error(resp, self.display_name)
        node = _first_node(resp, "response")
        rows = []
        if isinstance(node, dict):
            result_list = node.get("result_list") or {}
            map_data = result_list.get("map_data") or result_list.get("data") or []
            if isinstance(map_data, dict):
                map_data = map_data.get("item") or []
            rows = map_data if isinstance(map_data, list) else []
        return self._parse_items(rows, keyword, page_size)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_material(category or self.default_category, 1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        return self._call_material(keyword, 1, min(limit, 100))

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("item_id") or g.get("num_iid") or "")
            if not pid:
                continue
            price = to_float(g.get("zk_final_price") or g.get("reserve_price"))
            sales = to_int(g.get("volume") or g.get("total_sales"))
            coupon = to_float(g.get("coupon_amount"))
            promo = None
            if coupon:
                promo = f"领券立减 ¥{coupon:g}"
            elif g.get("coupon_info"):
                promo = clean_text(g.get("coupon_info"))
            products.append(
                Product(
                    platform="taobao_open",
                    product_id=pid,
                    title=clean_text(g.get("title") or "未命名商品"),
                    price=price,
                    original_price=to_float(g.get("reserve_price")),
                    sales=sales,
                    sales_text=f"30天销量 {sales}" if sales else None,
                    shop_name=clean_text(g.get("shop_title") or g.get("nick")),
                    rating=to_float(g.get("seller_credit_score")),
                    promo_text=promo,
                    is_promo=promo is not None,
                    rank=rank,
                    category=clean_text(g.get("category_name")) or category,
                    url=g.get("item_url") or f"https://item.taobao.com/item.htm?id={pid}",
                    image=g.get("pict_url") or g.get("item_pic_url"),
                )
            )
        if not products:
            raise CollectorError("淘宝物料搜索返回为空（检查关键词/淘宝客权限/是否已授权）")
        return products


# ---------------------------------------------------------------------------
# 3) 拼多多开放平台 —— pdd.ddk.goods.search（多多客商品搜索）
# ---------------------------------------------------------------------------
class PddOpenAdapter(OfficialAdapter):
    """拼多多开放平台官方 API：多多客商品搜索（选品/榜单）。

    签名：sign = md5(client_secret + 公共+业务参数按 ASCII 升序 key+value + client_secret) 大写。
    """

    platform = "pdd_open"
    display_name = "拼多多（官方 API）"
    regions = "国内"
    availability = "官方 API（已配置 ClientId/Secret）"
    supports_search = True
    default_category = "热销商品"
    credential_keys = ("PDD_CLIENT_ID", "PDD_CLIENT_SECRET")
    BASE = "https://gw-api.pinduoduo.com/api/router"

    def rank_categories(self) -> List[str]:
        return ["热销商品", "百货", "女装", "美妆", "数码", "食品", "母婴"]

    def _call_search(self, keyword: str, page: int, page_size: int) -> List[Product]:
        client_id, secret = self._get_credentials()
        params = {
            "type": "pdd.ddk.goods.search",
            "client_id": client_id,
            "timestamp": int(datetime.now().timestamp()),
            "data_type": "JSON",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "sort_type": 1,  # 0综合 1销量 2价格升 3价格降
        }
        params["sign"] = md5_sign(params, secret)
        resp = _loads(fetch_text(self.BASE, params=params), self.display_name)
        if resp.get("error_response"):
            err = resp["error_response"]
            raise CollectorError(f"拼多多错误 {err.get('error_code')}: {err.get('error_msg')}")
        node = resp.get("goods_search_response") or {}
        rows = node.get("goods_list") or []
        return self._parse_items(rows, keyword, page_size)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_search(category or self.default_category, 1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        return self._call_search(keyword, 1, min(limit, 100))

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("goods_id") or "")
            if not pid:
                continue
            price = _fen2yuan(to_float(g.get("min_group_price")))  # 单位分
            orig = _fen2yuan(to_float(g.get("min_normal_price")))
            coupon = to_float(g.get("coupon_discount"))
            promo = f"领券立减 ¥{coupon:g}" if coupon else None
            products.append(
                Product(
                    platform="pdd_open",
                    product_id=pid,
                    title=clean_text(g.get("goods_name") or "未命名商品"),
                    price=price,
                    original_price=orig,
                    sales=to_int(g.get("sales") or g.get("sold_quantity")),
                    sales_text=f"月销 {g.get('sales')}" if g.get("sales") is not None else None,
                    shop_name=clean_text(g.get("mall_name") or g.get("mall_id")),
                    promo_text=promo,
                    is_promo=promo is not None,
                    rank=rank,
                    category=clean_text(g.get("goods_type_name") or g.get("category_name")) or category,
                    url=f"https://mobile.yangkeduo.com/goods.html?goods_id={pid}",
                    image=g.get("goods_thumbnail_url") or g.get("goods_image_url"),
                )
            )
        if not products:
            raise CollectorError("拼多多商品搜索返回为空（检查 ClientId/Secret 权限：需开通多多客接口）")
        return products


# ---------------------------------------------------------------------------
# 4) 1688 开放平台 —— alibaba.product.search（阿里货源商品搜索）
# ---------------------------------------------------------------------------
class AlibabaOpenAdapter(OfficialAdapter):
    """1688 开放平台官方 API：商品搜索（找源头工厂货源）。

    签名（param2 风格）：_aop_signature = base64(HMAC-SHA1(app_secret, 参数升序 key+value 拼接))。
    需 access_token：配置 ALIBABA_ACCESS_TOKEN（开放平台后台应用授权后获取）。
    """

    platform = "alibaba_open"
    display_name = "1688（官方 API）"
    regions = "国内"
    availability = "官方 API（已配置 AppKey/Secret）"
    supports_search = True
    default_category = "源头货源"
    credential_keys = ("ALIBABA_APP_KEY", "ALIBABA_APP_SECRET")
    BASE = "https://gw.api.1688.com/openapi/param2/1/com.alibaba.product/alibaba.product.search/"

    def rank_categories(self) -> List[str]:
        return ["源头货源", "服装", "数码配件", "日用百货", "美妆个护", "食品", "家居"]

    def _call_search(self, keyword: str, page: int, page_size: int) -> List[Product]:
        app_key, secret = self._get_credentials()
        token = os.environ.get("ALIBABA_ACCESS_TOKEN", "")
        if not token:
            raise CollectorError(
                "1688 接口需要 access_token：请在 1688 开放平台应用后台完成授权后，"
                "把 token 填到配置项 ALIBABA_ACCESS_TOKEN（接口文档 → 配置中心 → 官方开放平台凭证）。"
            )
        params = {
            "access_token": token,
            "keywords": keyword,
            "pageSize": page_size,
            "pageNo": page,
            "orderBy": "volume:desc",  # 销量降序
        }
        params["_aop_signature"] = hmac_sha1_base64(params, secret)
        url = self.BASE + app_key
        resp = _loads(fetch_text(url, params=params), self.display_name)
        if "error" in resp or "error_code" in resp or resp.get("success") is False:
            msg = resp.get("error_message") or resp.get("message") or resp.get("error_code") or str(resp)[:200]
            raise CollectorError(f"1688 错误: {msg}")
        rows = []
        result = resp.get("result") or {}
        if isinstance(result, dict):
            rows = result.get("result") or result.get("items") or result.get("offerList") or []
        return self._parse_items(rows, keyword, page_size)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_search(category or self.default_category, 1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        return self._call_search(keyword, 1, min(limit, 100))

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("offerId") or g.get("offer_id") or "")
            if not pid:
                continue
            price = None
            price_info = g.get("priceInfo") or g.get("price_info") or []
            if isinstance(price_info, list) and price_info:
                price = to_float(price_info[0].get("price") if isinstance(price_info[0], dict) else price_info[0])
            elif isinstance(price_info, dict):
                price = to_float(price_info.get("price"))
            if price is None:
                price = to_float(g.get("price"))
            img = g.get("image") or g.get("picUrl") or g.get("img")
            if isinstance(img, list):
                img = img[0] if img else None
            products.append(
                Product(
                    platform="alibaba_open",
                    product_id=pid,
                    title=clean_text(g.get("subject") or g.get("title") or "未命名商品"),
                    price=price,
                    original_price=to_float(g.get("originalPrice") or g.get("referencePrice")),
                    sales=to_int(g.get("soldQuantity") or g.get("sales") or g.get("trade")),
                    sales_text=f"30天销量 {g.get('soldQuantity')}" if g.get("soldQuantity") is not None else None,
                    shop_name=clean_text(g.get("companyName") or g.get("sellerLoginId") or g.get("seller")),
                    brand=clean_text(g.get("brandName")),
                    stock_status="现货" if g.get("isSkuOffer") is not False else None,
                    rank=rank,
                    category=clean_text(g.get("categoryName")) or category,
                    url=f"https://detail.1688.com/offer/{pid}.html",
                    image=img,
                )
            )
        if not products:
            raise CollectorError("1688 商品搜索返回为空（检查关键词/权限/token 是否过期）")
        return products


# ---------------------------------------------------------------------------
# 5) 快手电商开放平台 —— open.goods.list（快手小店商品列表）
# ---------------------------------------------------------------------------
class KuaishouOpenAdapter(OfficialAdapter):
    """快手电商开放平台官方 API：商品列表（选品/店铺监控）。

    签名：md5(app_secret + 公共+业务参数按 ASCII 升序 key+value + app_secret) 大写。
    需 access_token：配置 KUAISHOU_ACCESS_TOKEN（开放平台应用授权后获取）。
    """

    platform = "kuaishou_open"
    display_name = "快手（官方 API）"
    regions = "国内"
    availability = "官方 API（已配置 AppKey/Secret）"
    supports_search = False
    default_category = "全部商品"
    credential_keys = ("KUAISHOU_APP_KEY", "KUAISHOU_APP_SECRET")
    BASE = "https://openapi.kwaixiaodian.com"

    def rank_categories(self) -> List[str]:
        return ["全部商品", "服饰", "美妆", "食品", "日用百货", "数码", "母婴"]

    def _call_goods(self, page: int, page_size: int) -> List[Product]:
        app_key, secret = self._get_credentials()
        token = os.environ.get("KUAISHOU_ACCESS_TOKEN", "")
        if not token:
            raise CollectorError(
                "快手接口需要 access_token：请在快手电商开放平台应用授权后，"
                "把 token 填到配置项 KUAISHOU_ACCESS_TOKEN（接口文档 → 配置中心 → 官方开放平台凭证）。"
            )
        method = "open.goods.list"
        params = {
            "appKey": app_key,
            "method": method,
            "version": "1",
            "signMethod": "MD5",
            "accessToken": token,
            "timestamp": str(int(datetime.now().timestamp() * 1000)),
            "param": sorted_json({"page": page, "pageSize": page_size}),
        }
        params["sign"] = md5_sign(params, secret)
        resp = _loads(fetch_text(self.BASE, params=params), self.display_name)
        if str(resp.get("result")) not in ("1", "0", None, "0"):
            raise CollectorError(f"快手错误 result={resp.get('result')}: {resp.get('error_msg') or resp.get('message')}")
        data = resp.get("data") or resp.get("resultData") or {}
        if isinstance(data, dict):
            rows = data.get("goodsList") or data.get("list") or data.get("items") or []
        else:
            rows = data if isinstance(data, list) else []
        return self._parse_items(rows, "全部商品", page_size)

    def fetch_rank(self, category: Optional[str] = None, limit: int = 20) -> List[Product]:
        return self._call_goods(1, min(limit, 100))

    def fetch_search(self, keyword: str, limit: int = 20) -> List[Product]:
        raise CollectorError("快手官方接口暂无商品搜索权限，请用商品列表/榜单")

    @staticmethod
    def _parse_items(rows: list, category: str, limit: int) -> List[Product]:
        products: List[Product] = []
        for rank, g in enumerate(rows[:limit], start=1):
            pid = str(g.get("goodsId") or g.get("id") or g.get("itemId") or "")
            if not pid:
                continue
            price = to_float(g.get("goodsPrice") or g.get("price"))
            products.append(
                Product(
                    platform="kuaishou_open",
                    product_id=pid,
                    title=clean_text(g.get("goodsName") or g.get("name") or "未命名商品"),
                    price=price,
                    original_price=to_float(g.get("marketPrice") or g.get("originalPrice")),
                    sales=to_int(g.get("sales") or g.get("sold")),
                    sales_text=f"销量 {g.get('sales')}" if g.get("sales") is not None else None,
                    shop_name=clean_text(g.get("shopName") or g.get("mallName") or "快手小店"),
                    stock_status="现货" if str(g.get("status")) == "1" else None,
                    rank=rank,
                    category=clean_text(g.get("categoryName")) or category,
                    url=f"https://c.kwaixiaodian.com/detail/{pid}",
                    image=g.get("goodsImg") or g.get("picUrl") or g.get("img"),
                )
            )
        if not products:
            raise CollectorError("快手返回为空（检查 AppKey/Secret 权限与 token 是否过期）")
        return products


# ---------------------------------------------------------------------------
# 公共小工具
# ---------------------------------------------------------------------------
def _fen2yuan(value: Optional[float]) -> Optional[float]:
    """分 -> 元（抖店/拼多多金额单位）。"""
    if value is None:
        return None
    return round(value / 100.0, 2)


def _loads(text: str, name: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CollectorError(f"{name} 返回非 JSON（可能被网关拦截或凭证错误）：{e}") from e
    return data if isinstance(data, dict) else {"data": data}


def _check_taobao_error(resp: dict, name: str) -> None:
    if "error_response" in resp:
        err = resp["error_response"]
        raise CollectorError(f"{name} 错误 code={err.get('code')}: {err.get('msg') or err.get('sub_msg')}")


def _first_node(resp: dict, suffix: str) -> Optional[dict]:
    for k, v in resp.items():
        if k.endswith(suffix) and isinstance(v, dict):
            return v
    return None


_ALL: List[type] = [
    DouyinMallAdapter,
    TaobaoOpenAdapter,
    PddOpenAdapter,
    AlibabaOpenAdapter,
    KuaishouOpenAdapter,
]


def all_official_adapters() -> List[OfficialAdapter]:
    return [cls() for cls in _ALL]
