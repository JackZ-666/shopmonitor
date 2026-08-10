"""适配器注册表：统一入口，按平台名取适配器。"""
from typing import Dict, List

from .base import CollectorError, PlatformAdapter
from .mock import MockAdapter

_ADAPTERS: Dict[str, PlatformAdapter] = {}


def _register_all() -> None:
    from .aliexpress import AliExpressAdapter
    from .amazon import AmazonAdapter
    from .douyin import DouyinAdapter
    from .jd import JDAdapter
    from .pdd import PDDAdapter
    from .shopee import ShopeeAdapter
    from .taobao import TaobaoAdapter
    from .official import (
        AlibabaOpenAdapter,
        DouyinMallAdapter,
        KuaishouOpenAdapter,
        PddOpenAdapter,
        TaobaoOpenAdapter,
    )
    from .official_global import (
        AliExpressOpenAdapter,
        AmazonOpenAdapter,
        ShopeeOpenAdapter,
        TikTokShopAdapter,
    )

    for cls in (
        MockAdapter,
        JDAdapter,
        PDDAdapter,
        DouyinAdapter,
        TaobaoAdapter,
        ShopeeAdapter,
        AmazonAdapter,
        AliExpressAdapter,
        DouyinMallAdapter,
        TaobaoOpenAdapter,
        PddOpenAdapter,
        AlibabaOpenAdapter,
        KuaishouOpenAdapter,
        TikTokShopAdapter,
        AmazonOpenAdapter,
        ShopeeOpenAdapter,
        AliExpressOpenAdapter,
    ):
        adapter = cls()
        _ADAPTERS[adapter.platform] = adapter

    # 京东联盟官方适配器（独立 key，不覆盖 jd 的 JSON 数据源）
    try:
        from .jd_union import JDUnionAdapter  # noqa: PLC0415
        _jdu = JDUnionAdapter()
        _jdu.platform = "jd_union"
        _ADAPTERS["jd_union"] = _jdu
    except Exception:  # noqa: BLE001
        pass



_register_all()


def get_adapter(platform: str) -> PlatformAdapter:
    key = platform.lower().strip()
    if key in _ADAPTERS:
        return _ADAPTERS[key]
    raise CollectorError(f"未知平台: {platform}，可用: {', '.join(_ADAPTERS)}")


def list_platforms() -> List[dict]:
    out = []
    for a in _ADAPTERS.values():
        out.append(
            {
                "platform": a.platform,
                "name": a.display_name,
                "regions": a.regions,
                "availability": a.availability,
                "supports_search": a.supports_search,
                "default_category": a.default_category,
                "categories": a.rank_categories(),
            }
        )
    return sorted(out, key=lambda x: (x["regions"] != "国内", x["platform"]))