"""价格/销量/评价 涨跌分析（取最近两次抓取对比）。"""
from typing import List, Optional

from .models import ChangeInfo, HistoryPoint


def _diff(now, before):
    """保留整数差值（销量/评论数返回 int，价格返回 float）。"""
    if now is None or before is None:
        return None
    if isinstance(now, int) and isinstance(before, int):
        return now - before
    return round(float(now) - float(before), 2)


def _pct(now, before) -> Optional[float]:
    if now is None or before is None or not before:
        return None
    return round((float(now) - float(before)) / float(before) * 100, 2)


def analyze_change(platform: str, product_id: str, history: List[HistoryPoint]) -> ChangeInfo:
    if not history:
        return ChangeInfo(platform=platform, product_id=product_id, note="暂无历史数据")
    now = history[0]
    if len(history) < 2:
        return ChangeInfo(
            platform=platform,
            product_id=product_id,
            price_now=now.price,
            sales_now=now.sales,
            rating_now=now.rating,
            note="只有 1 条记录，需再抓取一次才能计算涨跌",
        )
    before = history[1]
    price_change = _diff(now.price, before.price)
    price_change_pct = _pct(now.price, before.price)
    sales_change = _diff(now.sales, before.sales)
    sales_change_pct = _pct(now.sales, before.sales)
    review_change = _diff(now.review_count, before.review_count)

    if sales_change is not None and sales_change > 0:
        direction = "up"
    elif sales_change is not None and sales_change < 0:
        direction = "down"
    elif price_change is not None and price_change < 0:
        direction = "down"  # 降价
    elif price_change is not None and price_change > 0:
        direction = "up"    # 涨价
    else:
        direction = "flat"

    note_parts = []
    if price_change is not None:
        note_parts.append(("降价" if price_change < 0 else "涨价" if price_change > 0 else "价格持平") + f" {abs(price_change):.2f}")
    if sales_change is not None:
        note_parts.append(("销量" + ("↑" if sales_change > 0 else "↓" if sales_change < 0 else "→")) + f" {abs(sales_change)}")
    if review_change is not None:
        note_parts.append(("评论" + ("↑" if review_change > 0 else "↓" if review_change < 0 else "→")) + f" {abs(review_change)}")

    return ChangeInfo(
        platform=platform,
        product_id=product_id,
        price_now=now.price,
        price_before=before.price,
        price_change=price_change,
        price_change_pct=price_change_pct,
        sales_now=now.sales,
        sales_before=before.sales,
        sales_change=sales_change,
        sales_change_pct=sales_change_pct,
        rating_now=now.rating,
        review_change=review_change,
        direction=direction,
        note="；".join(note_parts) if note_parts else "无明显变化",
    )


# 平台默认佣金率（用于商品级预估毛利：对比表/日报/潜力筛选）
COMMISSION_RATES = {
    "amazon": 0.15, "amazon_open": 0.15, "shopee": 0.06, "shopee_open": 0.06,
    "aliexpress": 0.08, "aliexpress_open": 0.08, "taobao": 0.05, "taobao_open": 0.05,
    "douyin": 0.05, "douyin_mall": 0.05, "jd": 0.03, "pdd": 0.006, "pdd_open": 0.006,
    "kuaishou_open": 0.05, "alibaba_open": 0.05, "tiktok_shop": 0.06, "mock": 0.05,
}


# 排名 -> 预估月销 模型（各平台 Top1 基准销量 + 排名衰减指数；无销量时用排名估算）
_SALES_BASE = {"amazon": 20000, "shopee": 8000, "aliexpress": 6000, "taobao": 8000, "jd": 6000,
               "pdd": 10000, "douyin": 9000, "tiktok_shop": 7000, "mock": 5000}
_SALES_ALPHA = 0.8


def estimate_monthly_sales(platform: str, rank=None, sales=None):
    """预估月销：有销量用销量；否则按 排名 用 base / rank^alpha 估算。"""
    if sales is not None:
        try:
            return int(sales)
        except (TypeError, ValueError):
            pass
    if not rank or rank <= 0:
        return None
    base = _SALES_BASE.get(platform, 5000)
    return max(1, int(base / (float(rank) ** _SALES_ALPHA)))


def estimate_item_profit(
    price,
    platform: str,
    cost_rate: float = 0.4,
    shipping: float = 0.0,
    acos: float = 0.0,
    duty_rate: float = 0.0,
    return_rate: float = 0.0,
):
    """按售价粗估毛利：售价×(1−佣金−其他1%−ACOS) − 成本×(1+关税) − 售价×退货率 − 运费。

    duty_rate 为进口关税占采购成本比例；return_rate 为退货/退款率（按全损简化）。
    返回 (预估毛利, 预估毛利率%)；价格缺失返回 (None, None)。
    """
    if price is None:
        return None, None
    price = float(price)
    comm = COMMISSION_RATES.get(platform, 0.05)
    cost = price * cost_rate
    est = (price * (1 - comm - 0.01 - acos)
           - cost * (1 + duty_rate) - price * return_rate - shipping)
    margin = est / price * 100 if price else 0.0
    return round(est, 2), round(margin, 1)


# ---------------- 毛利估算（选品定价工具） ----------------
def estimate_profit(
    sale_price: float,
    cost: float,
    shipping: float = 0.0,
    commission_rate: float = 0.05,
    other_rate: float = 0.01,
    tax_rate: float = 0.0,
    quantity: int = 1,
    currency: str = "CNY",
    fx_rate: Optional[float] = None,
    fulfillment: str = "手动",
    fulfillment_fee: float = 0.0,
    storage_fee: float = 0.0,
    payment_fee_rate: float = 0.0,
    fx_loss_rate: float = 0.0,
    packaging_fee: float = 0.0,
    acos_rate: float = 0.0,
    long_storage_fee: float = 0.0,
    removal_fee: float = 0.0,
    duty_rate: float = 0.0,
    return_rate: float = 0.0,
    fixed_fee: float = 0.0,
) -> dict:
    """按件估算：佣金/其他/税费/履约费/仓储费/长期仓储费/移除费/收付费/汇损/打包费/广告费 -> 毛利/毛利率/ROI。

    口径：
    - 费用（外币）：佣金=售价×佣金率；其他=售价×其他率；税=售价×税率；
      履约费=fulfillment_fee×件数（如 Amazon FBA 履行费）；月仓储费=storage_fee×件数；
      长期仓储费=long_storage_fee×件数（如 Amazon 超龄库存费）；移除/弃置费=removal_fee×件数；
      收款手续费=售价×件数×payment_fee_rate。
    - 人民币：广告费=收入折人民币×acos_rate（ACOS）；汇损=收入折人民币×fx_loss_rate；
      成本=（采购成本+运费+打包费）×件数。
    - 总成本=人民币成本 + 外币费用折人民币 + 广告费 + 汇损；毛利=收入折人民币-总成本；
      ROI=毛利/(成本+运费+打包)×100%。

    跨境：currency 为结算币种（如 USD）；售价/履约费/仓储费/长期仓储费/移除费按结算币种填，
    采购成本/运费/打包费按人民币填；fx_rate 为「1 外币=多少人民币」，留空自动取实时汇率。
    fulfillment 仅为展示标签（如 Amazon FBA / FBM），预设见 fulfillment.py。
    """
    code = (currency or "CNY").upper()
    fx = 1.0
    fx_source = "人民币"
    if code != "CNY":
        from .currencies import get_rate, get_rates  # noqa: PLC0415
        fx = float(fx_rate) if fx_rate else get_rate(code)
        fx_source = "手动" if fx_rate else get_rates()["source"]

    sale_total_local = sale_price * quantity                  # 结算币种收入
    commission_local = sale_price * commission_rate * quantity
    other_local = sale_price * other_rate * quantity
    tax_local = sale_price * tax_rate * quantity
    fulfillment_local = fulfillment_fee * quantity            # 履约费（FBA 等）
    storage_local = storage_fee * quantity                    # 月仓储费
    long_storage_local = long_storage_fee * quantity          # 长期仓储费（超龄库存）
    removal_local = removal_fee * quantity                    # 移除/弃置费
    payment_local = sale_total_local * payment_fee_rate       # 收款/结汇手续费
    fees_local = (commission_local + other_local + tax_local + fulfillment_local
                  + storage_local + long_storage_local + removal_local)

    sale_total_cny = sale_total_local * fx
    payment_cny = payment_local * fx
    fees_cny = fees_local * fx + payment_cny
    cost_cny = (cost + shipping + packaging_fee) * quantity   # 人民币成本
    fx_loss_cny = sale_total_cny * fx_loss_rate               # 汇损
    ad_cny = sale_total_cny * acos_rate                       # 广告费（ACOS）
    duty_cny = cost_cny * duty_rate                           # 进口关税（占成本）
    return_cny = sale_total_cny * return_rate                 # 退货/退款损失（按全损简化）
    fixed_fee_cny = fixed_fee * fx                            # 一次性固定费（如月租/保证金分摊）
    total_cost = cost_cny + fees_cny + ad_cny + fx_loss_cny + duty_cny + return_cny + fixed_fee_cny
    gross_profit = sale_total_cny - total_cost
    gross_margin = gross_profit / sale_total_cny * 100 if sale_total_cny else 0.0
    invest = cost_cny if cost_cny else 1.0
    roi = gross_profit / invest * 100

    return {
        "sale_price": round(sale_price, 2),
        "quantity": quantity,
        "sale_total": round(sale_total_local, 2),              # 结算币种收入
        "sale_total_cny": round(sale_total_cny, 2),
        "cost": round(cost, 2),
        "shipping": round(shipping, 2),
        "commission": round(commission_local, 2),
        "commission_rate": commission_rate,
        "other_fee": round(other_local, 2),
        "tax": round(tax_local, 2),
        "fulfillment": fulfillment,
        "fulfillment_fee": round(fulfillment_local, 2),
        "storage_fee": round(storage_local, 2),
        "long_storage_fee": round(long_storage_local, 2),
        "removal_fee": round(removal_local, 2),
        "payment_fee": round(payment_local, 2),
        "payment_fee_rate": payment_fee_rate,
        "fx_loss": round(fx_loss_cny, 2),
        "fx_loss_rate": fx_loss_rate,
        "packaging_fee": round(packaging_fee * quantity, 2),
        "ad_fee": round(ad_cny, 2),
        "ad_fee_rate": acos_rate,
        "duty": round(duty_cny, 2),
        "duty_rate": duty_rate,
        "return_cost": round(return_cny, 2),
        "return_rate": return_rate,
        "fixed_fee": round(fixed_fee_cny, 2),
        "total_cost": round(total_cost, 2),                    # 人民币口径
        "gross_profit": round(gross_profit, 2),                # 人民币口径（兼容旧字段）
        "gross_margin": round(gross_margin, 2),
        "roi": round(roi, 2),
        "currency": code,
        "fx_rate": round(fx, 4),
        "fx_source": fx_source,
        "fees_cny": round(fees_cny, 2),
        "gross_profit_local": round(gross_profit / fx, 2) if fx else round(gross_profit, 2),
    }

