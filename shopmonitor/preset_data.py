# -*- coding: utf-8 -*-
"""预置数据（免配置模式）：7 大平台内置真实感样例数据。

客户不配置任何 API 也能看到各平台榜单；一键启用后把 SHOPMONITOR_*_RANK_URL
指向这些文件。等客户有官方凭证后，可在配置中心一键换回官方 API。
"""
import json
from pathlib import Path

PRESET_PRODUCTS = {
    "jd": [
        ("1001", "Apple iPhone 15 Pro 5G手机 256G", 7999.0, 82000, "京东自营", "https://item.jd.com/1001.html"),
        ("1002", "小米 Redmi K70 5G手机", 2499.0, 120000, "小米京东自营旗舰店", "https://item.jd.com/1002.html"),
        ("1003", "华为 Mate 60 手机 512G", 5499.0, 65000, "华为京东自营旗舰店", "https://item.jd.com/1003.html"),
        ("1004", "海尔 501L 对开门冰箱", 3599.0, 28000, "海尔京东自营旗舰店", "https://item.jd.com/1004.html"),
        ("1005", "联想拯救者 Y7000P 游戏本", 7299.0, 15000, "联想京东自营旗舰店", "https://item.jd.com/1005.html"),
        ("1006", "美的 1.5匹 变频空调", 2699.0, 34000, "美的京东自营旗舰店", "https://item.jd.com/1006.html"),
        ("1007", "飞利浦 电动牙刷 声波款", 299.0, 90000, "飞利浦京东自营旗舰店", "https://item.jd.com/1007.html"),
        ("1008", "戴森 V12 无线吸尘器", 3990.0, 12000, "戴森京东自营旗舰店", "https://item.jd.com/1008.html"),
    ],
    "taobao": [
        ("2001", "夏季新款 法式碎花连衣裙 女", 129.0, 45000, "衣美旗舰店", "https://item.taobao.com/item.htm?id=2001"),
        ("2002", "纯棉短袖T恤 男女同款 基础款", 39.9, 120000, "棉质优选专营店", "https://item.taobao.com/item.htm?id=2002"),
        ("2003", "女士凉鞋 坡跟 软底 夏季", 89.0, 60000, "鞋行天下旗舰店", "https://item.taobao.com/item.htm?id=2003"),
        ("2004", "大容量保温杯 316不锈钢 500ml", 69.0, 80000, "杯具人生旗舰店", "https://item.taobao.com/item.htm?id=2004"),
        ("2005", "智能手环 心率监测 防水", 119.0, 55000, "数码潮品专营店", "https://item.taobao.com/item.htm?id=2005"),
        ("2006", "儿童益智积木 大颗粒 拼装", 99.0, 42000, "贝乐玩具旗舰店", "https://item.taobao.com/item.htm?id=2006"),
        ("2007", "厨房收纳置物架 多层 免打孔", 59.0, 70000, "家简生活旗舰店", "https://item.taobao.com/item.htm?id=2007"),
        ("2008", "防晒霜 SPF50+ 清爽不油腻", 89.0, 95000, "美肌日记旗舰店", "https://item.taobao.com/item.htm?id=2008"),
    ],
    "pdd": [
        ("3001", "一次性洗脸巾 加厚 100抽*3包", 9.9, 500000, "优选日用百货", "https://mobile.yangkeduo.com/goods.html?goods_id=3001"),
        ("3002", "手机壳 苹果全系 透明防摔", 6.8, 800000, "潮壳数码专营店", "https://mobile.yangkeduo.com/goods.html?goods_id=3002"),
        ("3003", "数据线 三合一 快充 2米", 8.5, 650000, "简充数码", "https://mobile.yangkeduo.com/goods.html?goods_id=3003"),
        ("3004", "厨房湿巾 去油污 80抽*5包", 12.9, 480000, "洁净生活馆", "https://mobile.yangkeduo.com/goods.html?goods_id=3004"),
        ("3005", "收纳箱 大号 加厚 带轮", 19.9, 360000, "家装优选", "https://mobile.yangkeduo.com/goods.html?goods_id=3005"),
        ("3006", "袜子 男士 纯棉 5双装", 9.9, 720000, "日用品工厂店", "https://mobile.yangkeduo.com/goods.html?goods_id=3006"),
        ("3007", "车载手机支架 重力感应", 15.8, 420000, "车品专营店", "https://mobile.yangkeduo.com/goods.html?goods_id=3007"),
        ("3008", "玻璃杯 带盖 大容量 家用", 7.9, 390000, "居家百货汇", "https://mobile.yangkeduo.com/goods.html?goods_id=3008"),
    ],
    "douyin": [
        ("4001", "抖音爆款 无线蓝牙耳机 降噪", 69.9, 180000, "声动数码旗舰店", "https://haohuo.jinritemai.com/views/product/item2?id=4001"),
        ("4002", "网红气垫梳 顺发 蓬松 按摩", 19.9, 260000, "美发工坊", "https://haohuo.jinritemai.com/views/product/item2?id=4002"),
        ("4003", "即食螺蛳粉 柳州风味 3包", 29.9, 320000, "舌尖工厂直供", "https://haohuo.jinritemai.com/views/product/item2?id=4003"),
        ("4004", "免打孔挂钩 强力 浴室厨房", 9.9, 450000, "家清百货", "https://haohuo.jinritemai.com/views/product/item2?id=4004"),
        ("4005", "便携榨汁杯 无线 充电 随行杯", 59.0, 150000, "生活好物局", "https://haohuo.jinritemai.com/views/product/item2?id=4005"),
        ("4006", "发热围巾 充电 保暖 冬季", 89.0, 98000, "暖冬优选", "https://haohuo.jinritemai.com/views/product/item2?id=4006"),
        ("4007", "迷你手持挂烫机 便携", 49.9, 130000, "家居小电器", "https://haohuo.jinritemai.com/views/product/item2?id=4007"),
        ("4008", "猫粮 全价 冻干双拼 1.8kg", 89.0, 210000, "萌宠粮仓", "https://haohuo.jinritemai.com/views/product/item2?id=4008"),
    ],
    "shopee": [
        ("5001", "Wireless Bluetooth Earbuds TWS", 39.9, 120000, "TechPro Store", "https://shopee.com/product/1/5001"),
        ("5002", "Phone Case Silicone Anti-drop", 6.5, 260000, "CaseHub MY", "https://shopee.com/product/1/5002"),
        ("5003", "Portable Mini Fan USB Rechargeable", 12.0, 150000, "CoolBreeze", "https://shopee.com/product/1/5003"),
        ("5004", "LED Strip Lights 5m RGB", 15.5, 98000, "GlowShop", "https://shopee.com/product/1/5004"),
        ("5005", "Women Casual Dress Summer", 18.9, 130000, "Fashion Mall", "https://shopee.com/product/1/5005"),
        ("5006", "Car Phone Holder Gravity", 9.9, 110000, "AutoGear", "https://shopee.com/product/1/5006"),
        ("5007", "Kitchen Storage Box Set", 14.9, 87000, "HomePlus", "https://shopee.com/product/1/5007"),
        ("5008", "Pet Grooming Brush Cat Dog", 7.8, 76000, "PetCare", "https://shopee.com/product/1/5008"),
    ],
    "amazon": [
        ("B0TEST01", "Wireless Earbuds Bluetooth 5.3 Noise Cancelling", 29.99, 45000, "SoundPeats", "https://www.amazon.com/dp/B0TEST01"),
        ("B0TEST02", "iPhone Charger 20W USB-C Fast Charging", 16.99, 38000, "Anker", "https://www.amazon.com/dp/B0TEST02"),
        ("B0TEST03", "Stainless Steel Water Bottle 32oz Insulated", 24.99, 29000, "HydroLife", "https://www.amazon.com/dp/B0TEST03"),
        ("B0TEST04", "Memory Foam Pillow Cooling Cervical Support", 39.99, 21000, "DreamSleep", "https://www.amazon.com/dp/B0TEST04"),
        ("B0TEST05", "LED Desk Lamp Dimmable USB Rechargeable", 27.99, 18000, "BrightHome", "https://www.amazon.com/dp/B0TEST05"),
        ("B0TEST06", "Robot Vacuum Cleaner 3-in-1", 159.99, 9500, "iRobot", "https://www.amazon.com/dp/B0TEST06"),
        ("B0TEST07", "Yoga Mat Non Slip 6mm Exercise", 25.99, 16000, "FitLife", "https://www.amazon.com/dp/B0TEST07"),
        ("B0TEST08", "Electric Kettle 1.7L Stainless Steel", 34.99, 14000, "Cuisinart", "https://www.amazon.com/dp/B0TEST08"),
    ],
    "aliexpress": [
        ("1005001", "Smart Watch Fitness Tracker Heart Rate", 22.99, 52000, "GlobalTech Store", "https://www.aliexpress.com/item/1005001.html"),
        ("1005002", "Wireless Earbuds TWS LED Display", 18.99, 47000, "AudioZone", "https://www.aliexpress.com/item/1005002.html"),
        ("1005003", "LED Neon Sign Customizable Wall Light", 15.99, 33000, "GlowDeco", "https://www.aliexpress.com/item/1005003.html"),
        ("1005004", "Car Vacuum Cleaner Portable 12V", 21.99, 28000, "AutoClean", "https://www.aliexpress.com/item/1005004.html"),
        ("1005005", "Waterproof Phone Pouch Universal", 6.99, 61000, "OutdoorPro", "https://www.aliexpress.com/item/1005005.html"),
        ("1005006", "3D Printer Filament PLA 1.75mm", 16.99, 24000, "3DSupply", "https://www.aliexpress.com/item/1005006.html"),
        ("1005007", "Sunglasses UV400 Polarized", 9.99, 58000, "SunStyle", "https://www.aliexpress.com/item/1005007.html"),
        ("1005008", "Mini Projector 1080P Portable", 49.99, 19000, "HomeCinema", "https://www.aliexpress.com/item/1005008.html"),
    ],
}

FILE_MAP = {
    "jd": "jd.json", "taobao": "taobao.json", "pdd": "pdd.json", "douyin": "douyin.json",
    "shopee": "shopee.json", "amazon": "amazon.json", "aliexpress": "aliexpress.json",
}


def preset_dir(base: Path) -> Path:
    return base / "data" / "预置数据"


def ensure_preset_files(base: Path) -> int:
    """生成 7 平台预置数据 JSON 文件，返回生成数量。"""
    d = preset_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for platform, fname in FILE_MAP.items():
        rows = []
        for rank, (pid, title, price, sales, shop, url) in enumerate(PRESET_PRODUCTS[platform], start=1):
            rows.append({
                "product_id": pid, "title": title, "price": price,
                "original_price": round(price * 1.35, 2), "sales": sales,
                "sales_text": f"销量 {sales}", "rating": 4.7, "review_count": int(sales * 0.3),
                "stock_status": "现货", "is_promo": rank <= 2,
                "promo_text": "限时折扣" if rank <= 2 else None,
                "shop_name": shop, "shop_rating": 4.8, "rank": rank, "category": "预置",
                "url": url,
            })
        (d / fname).write_text(json.dumps({"items": rows, "source": "预置数据",
                                           "note": "免配置预置样例，可在配置中心一键换官方 API"},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    (d / "说明.txt").write_text(
        "预置数据：7 大平台免配置样例，用于不配置 API 也能体验完整面板。\n"
        "在「接口文档 → 配置中心」点「一键启用预置数据」即可自动生效；\n"
        "有官方凭证后，在配置中心替换对应平台即可切真实数据。\n", encoding="utf-8")
    return n
