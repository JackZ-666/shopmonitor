---
name: shopmonitor-sku-monitor
description: 电商选品与竞品监控。当需要跨平台（京东/拼多多/淘宝/抖音/Shopee/Amazon/AliExpress）获取商品榜单、搜索商品、监控价格与销量历史、生成选品对比表，或调用 UUMit 免费电商数据时使用。先启动本地 ShopMonitor API（python run_api.py），再调用其 HTTP 接口。
version: 0.1.0
user-invocable: true
homepage: https://m.uumit.com
---

# ShopMonitor 电商选品/竞品监控 Skill

跨平台电商数据采集与选品分析能力，供 Agent 调用本地 ShopMonitor API 完成：
- 榜单/热卖数据：`GET /api/v1/rank/{platform}?category=...`
- 关键词搜索：`GET /api/v1/search/{platform}?keyword=...`
- 价格/销量历史：`GET /api/v1/product/{platform}/{id}/history`
- 选品对比表：`GET /api/v1/report/compare?platform=...&product_ids=...&fmt=md|csv|xlsx`
- UUMit 免费电商数据：`GET /api/v1/uumit/free-data`、`POST /api/v1/uumit/data/{api_id}/call`

## 何时使用
- 用户要"看看某平台卖得好的商品 / 对比几个商品 / 监控降价 / 出一份选品报告"
- 需要跨平台榜单、销量、价格、店铺等电商数据

## 前置条件
1. 本地已启动 ShopMonitor API（默认 `http://127.0.0.1:8000`）
2. 平台真实数据按 `docs/PLATFORM_STATUS.md` 配置（未配置的平台自动返回演示数据并标注 `degraded=true`）
3. UUMit 免费数据依赖本机 uumit-agent 技能授权

## 调用示例（Agent 内部执行）
```bash
# 1) 拉京东手机榜
curl "http://127.0.0.1:8000/api/v1/rank/jd?category=手机&limit=10"

# 2) 生成选品对比表
curl "http://127.0.0.1:8000/api/v1/report/compare?platform=mock&product_ids=demo-数码-0001,demo-数码-0002&fmt=md"

# 3) 调用 UUMit 免费电商数据（0 扣费）
curl -X POST "http://127.0.0.1:8000/api/v1/uumit/data/56838770-5c57-4d1b-80c7-93ed61b57f7a/call" \
  -H "Content-Type: application/json" \
  -d '{"grain":"month","dateFrom":"2024-01-01","dateTo":"2024-03-31"}'
```

## 输出规范
- 面向用户输出自然语言总结（榜单 Top N、关键价格/销量变化、对比结论），不粘贴原始 JSON。
- 对比报告默认 Markdown 表格；需要 Excel/CSV 时用 `fmt=csv|xlsx`。

## 合规与安全
- 只采集公开可见数据，遵守各平台 robots/ToS，控制频率（套件内置限流）。
- UUMit 免费数据只调 `price_ut=0` 的接口；付费接口返回 `needs_confirmation`，需用户确认后才允许调用。
- 不输出任何 API Key / Token / 账号类敏感信息。