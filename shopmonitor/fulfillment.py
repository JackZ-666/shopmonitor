"""各平台运营/发货模式预设（费用结构随模式变化，例如 Amazon FBA vs FBM）。

用途：毛利计算器一键套用某平台的运营方式，自动带出佣金率/履约费/仓储费/税率等。
所有数值均为「示例默认」，实际请按类目佣金、重量尺寸、物流报价调整（界面可手动改）。

字段说明：
- key: 模式标识；name: 中文名；platform: 归属平台
- commission_rate: 平台佣金率（0.15=15%）
- other_rate: 其他费率（包装/支付/售后等，0.01=1%）
- tax_rate: 税率（国内增值税约 0.13；跨境多为 0）
- fulfillment_fee: 单位履约费（结算币种/件，如 Amazon FBA 履行费美元）
- storage_fee: 单位月仓储费（结算币种/件·月，海外仓/平台仓用）
- shipping_hint: 运费输入框的提示文案
"""
from typing import List, Optional

# Amazon FBA 履行费分档（美国站 2025 参考价，单位 USD/件；实际按最新价目表与旺季调整）
FBA_FULFILLMENT_TIERS: List[dict] = [
    {"key": "small_standard", "name": "小额标准（≤2oz）", "size": "≤45.7×33.9×19.6cm", "weight": "发货重≤2oz", "fee": 2.29},
    {"key": "large_standard_1lb", "name": "大额标准（≤1磅）", "size": "≤45.7×33.9×19.6cm", "weight": "发货重≤1lb", "fee": 5.06},
    {"key": "large_standard_2lb", "name": "大额标准（1-2磅）", "size": "≤45.7×33.9×19.6cm", "weight": "发货重 1-2lb", "fee": 6.65},
    {"key": "small_oversize", "name": "小额超规", "size": "最长边≤61cm 次长≤46cm 最短≤46cm", "weight": "体积重≤70lb", "fee": 9.37},
    {"key": "medium_oversize", "name": "中额超规", "size": "最长边≤122cm", "weight": "体积重≤150lb", "fee": 15.37},
    {"key": "large_oversize", "name": "大额超规（大件）", "size": "最长边≤244cm 或 次长≤122cm", "weight": "体积重≤150lb", "fee": 78.44},
]

# Amazon FBA 附加费参考（USD/件）
FBA_LONG_STORAGE_FEE_EXAMPLE = 0.15   # 超龄库存（271-365 天）约 $0.15/件·月
FBA_REMOVAL_FEE_EXAMPLE = 0.55        # 移除费（标准件）约 $0.50-$0.60/件；弃置约 $0.15-$0.30

FULFILLMENT_MODES: List[dict] = [
    # ---------------- Amazon（结算币种一般为 USD/EUR/GBP…） ----------------
    {"key": "amazon_fba", "platform": "amazon_open", "name": "Amazon FBA（亚马逊物流）",
     "commission_rate": 0.15, "other_rate": 0.0, "tax_rate": 0.0,
     "fulfillment_fee": 5.5, "storage_fee": 0.75,
     "long_storage_fee": 0.15, "removal_fee": 0.55,
     "duty_rate": 0.0, "return_rate": 0.05,
     "shipping_hint": "头程/国际物流费（人民币/件）；超龄仓储/移除费见高级费用"},
    {"key": "amazon_fbm", "platform": "amazon_open", "name": "Amazon FBM（自发货）",
     "commission_rate": 0.15, "other_rate": 0.01, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.05,
     "shipping_hint": "国际运费（人民币/件，由你承担）"},

    # ---------------- TikTok Shop ----------------
    {"key": "tts_platform", "platform": "tiktok_shop", "name": "TikTok 平台物流/官方仓",
     "commission_rate": 0.06, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 2.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.04,
     "shipping_hint": "头程物流费（人民币/件）"},
    {"key": "tts_self", "platform": "tiktok_shop", "name": "TikTok 自发货",
     "commission_rate": 0.06, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.04,
     "shipping_hint": "国际运费（人民币/件，由你承担）"},
    {"key": "tts_oversea", "platform": "tiktok_shop", "name": "TikTok 海外仓",
     "commission_rate": 0.06, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.8,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.04,
     "shipping_hint": "头程物流费（人民币/件；仓储费已另算）"},

    # ---------------- Shopee ----------------
    {"key": "shopee_sls", "platform": "shopee_open", "name": "Shopee 官方物流 SLS",
     "commission_rate": 0.06, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.03,
     "shipping_hint": "SLS 运费多由买家支付；需卖家承担的部分填这里（人民币/件）"},
    {"key": "shopee_self", "platform": "shopee_open", "name": "Shopee 自发货",
     "commission_rate": 0.06, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.03,
     "shipping_hint": "国际运费（人民币/件，由你承担）"},
    {"key": "shopee_oversea", "platform": "shopee_open", "name": "Shopee 海外仓",
     "commission_rate": 0.06, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.8,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.03,
     "shipping_hint": "头程物流费（人民币/件；仓储费已另算）"},

    # ---------------- AliExpress ----------------
    {"key": "ae_cainiao", "platform": "aliexpress_open", "name": "AliExpress 菜鸟官方物流",
     "commission_rate": 0.08, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 1.5, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.04,
     "shipping_hint": "官方物流费多在货款中扣；需卖家承担的填这里（人民币/件）"},
    {"key": "ae_self", "platform": "aliexpress_open", "name": "AliExpress 自发货",
     "commission_rate": 0.08, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.04,
     "shipping_hint": "国际小包运费（人民币/件）"},
    {"key": "ae_oversea", "platform": "aliexpress_open", "name": "AliExpress 海外仓/半托管",
     "commission_rate": 0.08, "other_rate": 0.03, "tax_rate": 0.0,
     "fulfillment_fee": 0.0, "storage_fee": 0.8,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.04,
     "shipping_hint": "头程物流费（人民币/件；仓储费已另算）"},

    # ---------------- 国内平台 ----------------
    {"key": "jd_self", "platform": "jd", "name": "京东自营/入仓（JDL）",
     "commission_rate": 0.03, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.5,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "入仓物流费（人民币/件）"},
    {"key": "jd_pop", "platform": "jd", "name": "京东 POP（商家自发货）",
     "commission_rate": 0.03, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "快递费（人民币/件）"},
    {"key": "tb_stock", "platform": "taobao", "name": "淘宝/天猫 现货直发",
     "commission_rate": 0.05, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "快递费（人民币/件）"},
    {"key": "tb_dropship", "platform": "taobao", "name": "淘宝/天猫 一件代发",
     "commission_rate": 0.05, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "代发运费（人民币/件，无库存压力）"},
    {"key": "pdd_stock", "platform": "pdd", "name": "拼多多 现货直发",
     "commission_rate": 0.006, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "快递费（人民币/件）"},
    {"key": "pdd_dropship", "platform": "pdd", "name": "拼多多 一件代发",
     "commission_rate": 0.006, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "代发运费（人民币/件）"},
    {"key": "dy_stock", "platform": "douyin", "name": "抖音小店 现货直发",
     "commission_rate": 0.05, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "快递费（人民币/件）"},
    {"key": "dy_dropship", "platform": "douyin", "name": "抖音小店 一件代发",
     "commission_rate": 0.05, "other_rate": 0.01, "tax_rate": 0.13,
     "fulfillment_fee": 0.0, "storage_fee": 0.0,
     "long_storage_fee": 0.0, "removal_fee": 0.0,
     "duty_rate": 0.0, "return_rate": 0.02,
     "shipping_hint": "代发运费（人民币/件）"},
]


# 类目预设：按类目自动带出高级费用（目前带 ACOS；后续可扩展退货率/广告预算）
CATEGORY_PRESETS: List[dict] = [
    {"key": "apparel", "name": "服装鞋包", "acos_rate": 0.20, "note": "服饰类广告竞争高，ACOS 参考 20%"},
    {"key": "beauty", "name": "美妆个护", "acos_rate": 0.18, "note": "美妆类 ACOS 参考 18%"},
    {"key": "digital", "name": "3C数码", "acos_rate": 0.12, "note": "数码类 ACOS 参考 12%"},
    {"key": "home", "name": "家居", "acos_rate": 0.12, "note": "家居类 ACOS 参考 12%"},
    {"key": "food", "name": "食品", "acos_rate": 0.10, "note": "食品类 ACOS 参考 10%"},
    {"key": "toy", "name": "玩具", "acos_rate": 0.15, "note": "玩具类 ACOS 参考 15%"},
    {"key": "outdoor", "name": "户外运动", "acos_rate": 0.12, "note": "户外类 ACOS 参考 12%"},
    {"key": "baby", "name": "母婴", "acos_rate": 0.15, "note": "母婴类 ACOS 参考 15%"},
]


def get_category_presets() -> List[dict]:
    return CATEGORY_PRESETS


def get_category_preset(key: str) -> Optional[dict]:
    for c in CATEGORY_PRESETS:
        if c["key"] == key:
            return dict(c)
    return None


# 整套费用模板：一键带入 币种/运营模式/FBA分档/佣金/物流/仓储/广告/关税/退货 等全部参数
FULL_TEMPLATES: List[dict] = [
    {"key": "amazon_fba_small", "name": "Amazon 美国·FBA标准件", "mode": "amazon_fba", "currency": "USD", "tier": "large_standard_1lb",
     "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 1.0, "acos_rate": 0.15,
     "duty_rate": 0.0, "return_rate": 0.05, "fixed_fee": 0.0, "note": "头程自理；履行费按大额标准≤1磅约 $5.06"},
    {"key": "amazon_fba_oversize", "name": "Amazon 美国·FBA大件", "mode": "amazon_fba", "currency": "USD", "tier": "large_oversize",
     "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 2.0, "acos_rate": 0.15,
     "duty_rate": 0.0, "return_rate": 0.05, "fixed_fee": 0.0, "note": "履行费按大额超规约 $78.44，头程自理"},
    {"key": "amazon_fbm", "name": "Amazon 美国·FBM自发货", "mode": "amazon_fbm", "currency": "USD", "tier": "",
     "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 1.0, "acos_rate": 0.15,
     "duty_rate": 0.0, "return_rate": 0.05, "fixed_fee": 0.0, "note": "国际运费自理，无 FBA 履行/仓储费"},
    {"key": "tts_us_platform", "name": "TikTok 美区·平台物流", "mode": "tts_platform", "currency": "USD", "tier": "",
     "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 1.0, "acos_rate": 0.12,
     "duty_rate": 0.0, "return_rate": 0.04, "fixed_fee": 0.0, "note": "平台物流，履约费约 $2/件"},
    {"key": "tts_sea_oversea", "name": "TikTok 东南亚·海外仓", "mode": "tts_oversea", "currency": "MYR", "tier": "",
     "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 1.0, "acos_rate": 0.12,
     "duty_rate": 0.0, "return_rate": 0.04, "fixed_fee": 0.0, "note": "马来西亚站 MYR 结算，海外仓仓储费另算"},
    {"key": "shopee_my_sls", "name": "Shopee 马来·SLS官方物流", "mode": "shopee_sls", "currency": "MYR", "tier": "",
     "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 1.0, "acos_rate": 0.10,
     "duty_rate": 0.0, "return_rate": 0.03, "fixed_fee": 0.0, "note": "MYR 结算；SLS 运费多由买家支付"},
    {"key": "shopee_br_oversea", "name": "Shopee 巴西·海外仓", "mode": "shopee_oversea", "currency": "BRL", "tier": "",
     "payment_fee_rate": 0.01, "fx_loss_rate": 0.01, "packaging_fee": 1.0, "acos_rate": 0.12,
     "duty_rate": 0.0, "return_rate": 0.03, "fixed_fee": 0.0, "note": "BRL 结算；巴西收付费/汇损较高约 1%"},
    {"key": "ae_cainiao", "name": "AliExpress·菜鸟官方物流", "mode": "ae_cainiao", "currency": "USD", "tier": "",
     "payment_fee_rate": 0.005, "fx_loss_rate": 0.005, "packaging_fee": 1.0, "acos_rate": 0.10,
     "duty_rate": 0.0, "return_rate": 0.04, "fixed_fee": 0.0, "note": "USD 结算；官方物流费多在货款中扣"},
    {"key": "jd_self", "name": "京东·自营入仓", "mode": "jd_self", "currency": "CNY", "tier": "",
     "payment_fee_rate": 0.0, "fx_loss_rate": 0.0, "packaging_fee": 1.0, "acos_rate": 0.05,
     "duty_rate": 0.0, "return_rate": 0.02, "fixed_fee": 0.0, "note": "人民币结算；入仓物流 + 仓储费"},
    {"key": "taobao_dropship", "name": "淘宝/天猫·一件代发", "mode": "tb_dropship", "currency": "CNY", "tier": "",
     "payment_fee_rate": 0.0, "fx_loss_rate": 0.0, "packaging_fee": 0.0, "acos_rate": 0.08,
     "duty_rate": 0.0, "return_rate": 0.02, "fixed_fee": 0.0, "note": "人民币结算；无库存压力，代发运费自理"},
    {"key": "pdd_stock", "name": "拼多多·现货直发", "mode": "pdd_stock", "currency": "CNY", "tier": "",
     "payment_fee_rate": 0.0, "fx_loss_rate": 0.0, "packaging_fee": 1.0, "acos_rate": 0.05,
     "duty_rate": 0.0, "return_rate": 0.02, "fixed_fee": 0.0, "note": "人民币结算；佣金 0.6% 平台技术服务费"},
    {"key": "douyin_stock", "name": "抖音小店·现货直发", "mode": "dy_stock", "currency": "CNY", "tier": "",
     "payment_fee_rate": 0.0, "fx_loss_rate": 0.0, "packaging_fee": 1.0, "acos_rate": 0.10,
     "duty_rate": 0.0, "return_rate": 0.02, "fixed_fee": 0.0, "note": "人民币结算；内容电商广告 ACOS 偏高"},
]


def get_full_templates() -> List[dict]:
    return FULL_TEMPLATES


def get_full_template(key: str) -> Optional[dict]:
    for t in FULL_TEMPLATES:
        if t["key"] == key:
            return dict(t)
    return None


def get_fulfillment_modes(platform: Optional[str] = None) -> List[dict]:
    """返回全部或指定平台的运营/发货模式预设。"""
    if platform:
        return [m for m in FULFILLMENT_MODES if m["platform"] == platform]
    return FULFILLMENT_MODES


def get_mode(key: str) -> Optional[dict]:
    for m in FULFILLMENT_MODES:
        if m["key"] == key:
            return dict(m)
    return None
