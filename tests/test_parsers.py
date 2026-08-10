"""工具函数与适配器解析单测（不联网）。"""
from shopmonitor.collectors.env_json import parse_items_json
from shopmonitor.collectors.mock import MockAdapter
from shopmonitor.utils import clean_text, to_float, to_int


def test_to_float():
    assert to_float("¥1,299.00") == 1299.0
    assert to_float("12.99") == 12.99
    assert to_float(None) is None
    assert to_float("暂无") is None


def test_to_int():
    assert to_int("已拼 1.2万件") == 12000
    assert to_int("10万+") == 100000
    assert to_int("3.5亿") == 350000000
    assert to_int("1,234") == 1234
    assert to_int(None) is None


def test_clean_text():
    assert clean_text("  a\n  b  ") == "a b"
    assert clean_text(None) == ""


def test_mock_deterministic():
    a = MockAdapter().fetch_rank(category="数码", limit=5)
    b = MockAdapter().fetch_rank(category="数码", limit=5)
    assert [p.product_id for p in a] == [p.product_id for p in b]
    assert a[0].platform == "mock"
    assert all(p.price and p.sales for p in a)
    # 新监控字段已填充
    assert all(p.rating and p.review_count and p.stock_status for p in a)


def test_env_json_parse_full_fields():
    payload = {
        "items": [
            {
                "product_id": "A1", "title": "测试商品", "price": "12.5", "sales": "2.3万",
                "shop_name": "店", "shop_rating": "4.8", "brand": "B",
                "rating": "4.7", "review_count": "1234",
                "stock_status": "现货", "promo_text": "满减", "is_promo": "1",
            },
            {"id": "A2", "name": "另一个", "current_price": 9.9, "sold": 100},
        ]
    }
    rows = parse_items_json(payload, platform="pdd", category="数码", limit=10)
    assert len(rows) == 2
    a = rows[0]
    assert a.price == 12.5
    assert a.sales == 23000
    assert a.rating == 4.7
    assert a.review_count == 1234
    assert a.shop_rating == 4.8
    assert a.brand == "B"
    assert a.stock_status == "现货"
    assert a.promo_text == "满减"
    assert a.is_promo is True
    assert rows[1].product_id == "A2"
    assert rows[1].sales == 100


def test_jd_parse_fixture():
    from shopmonitor.collectors.jd import JDAdapter

    html = """
    <ul class="gl-warp clearfix">
      <li class="gl-item" data-sku="10001">
        <div class="p-name"><em>华为手机 Mate 60 8+256G</em></div>
        <div class="p-price"><strong><i>4999.00</i></strong></div>
        <div class="p-commit"><strong><a>2万+条评价</a></strong></div>
        <div class="p-shop"><a>华为京东自营官方旗舰店</a></div>
      </li>
      <li class="gl-item" data-sku="10002">
        <div class="p-name"><em>小米手机 14</em></div>
        <div class="p-price"><strong><i>3999</i></strong></div>
      </li>
    </ul>
    """
    items = JDAdapter()._parse_search_html(html, "手机", 10)
    assert len(items) == 2
    assert items[0].product_id == "10001"
    assert items[0].price == 4999.0
    assert items[0].sales == 20000
    assert items[0].title == "华为手机 Mate 60 8+256G"

def test_pdd_snapshot_parse():
    """拼多多真实数据快照可被统一解析器解析。"""
    import json as _json
    from pathlib import Path as _Path
    from shopmonitor.collectors.env_json import parse_items_json

    root = _Path(__file__).resolve().parent.parent
    fp = root / "data" / "拼多多榜-数据源.json"
    if not fp.exists():
        return
    payload = _json.loads(fp.read_text(encoding="utf-8"))
    rows = parse_items_json(payload, platform="pdd", category="拼多多收藏", limit=10)
    assert len(rows) >= 1
    assert rows[0].product_id and rows[0].title and rows[0].price
