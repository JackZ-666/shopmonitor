# 平台可用性状态与接入指引

> 探测日期：2026-08-09（本机网络实测）。真实采集受反爬影响，套件会自动降级为演示数据（响应 `degraded=true`）。

## 状态总表

| 平台 | 类型 | 当前状态 | 需要什么 |
|---|---|---|---|
| mock | 演示 | ✅ 默认可用 | 无（本地试跑/上架演示用） |
| 京东 jd | 国内 | ⚠️ 榜单需联盟授权 | 已可用 UUMit 免费大盘拿京东真实平台数据（商品数/均价/销量/评分，0 扣费）；商品榜需联盟 API 或自定义 JSON |
| 拼多多 pdd | 国内 | ❌ 需 anti-content 签名 | 拼多多开放平台，或 `SHOPMONITOR_PDD_RANK_URL` |
| 抖音电商 douyin | 国内 | ❌ 需 a_bogus 签名 | 巨量/电商开放平台，或 `SHOPMONITOR_DOUYIN_RANK_URL` |
| 淘宝 taobao | 国内 | ❌ 需登录态 | `TAOBAO_COOKIE`，或 `SHOPMONITOR_TAOBAO_RANK_URL` |
| Shopee | 跨境 | ⚠️ 官方适配器已内置 | 已内置 shopee_open（需 PartnerKey + 授权）；或 `SHOPMONITOR_SHOPEE_RANK_URL` |
| Amazon | 跨境 | ⚠️ 官方适配器已内置 | 已内置 amazon_open（需 AWS Key + 联盟 PartnerTag）；或 `SHOPMONITOR_AMAZON_RANK_URL` |
| AliExpress | 跨境 | ⚠️ 官方适配器已内置 | 已内置 aliexpress_open（需联盟 AppKey + 授权）；或 `SHOPMONITOR_ALIEXPRESS_RANK_URL` |
| UUMit 免费数据 | 平台 | ✅ 已实测可用 | 已接入 uumit-agent 技能；3 个免费电商接口已点亮（平台对比/经营概览/销售趋势，0 扣费） |

## 三种点亮真实数据的方式（按推荐排序）

### 方式 0：本地 JSON 文件 / 手动数据源（最省事，0 申请 0 成本）
不需要注册任何平台、不需要 key：
1. 打开项目根目录 **数据源模板.json**，把某平台 Top 商品按模板抄进去（10 分钟）；
2. 在 `配置文件.env` 里填：`SHOPMONITOR_JD_RANK_URL=C:/.../京东榜.json`（本地路径或 http 地址都行）；
3. 重启服务，该平台即显示真实数据。
> 适合先跑通商业模式/给买家演示；以后可换成官方 API 或第三方数据自动更新。


### 1. 官方开放平台 API（最合规，推荐）
- 京东联盟开放平台、淘宝开放平台/阿里妈妈、拼多多开放平台、抖音电商开放平台、Shopee Open Platform、Amazon PA-API。
- 申请到 API Key 后，写一个很小的采集脚本（本仓库已有 `shopmonitor/collectors/*.py` 适配器模板），把官方数据转成统一 JSON 结构，再配置环境变量即可。

### 2. 登录 Cookie（快速验证，注意账号风险）
- 淘宝：浏览器登录后复制 Cookie，设 `TAOBAO_COOKIE`。淘宝适配器已支持解析搜索页数据；可能触发滑块，需定期更新 Cookie。

### 3. 自定义 JSON 数据源（最快接入任何已有接口）
把任何接口/爬虫/第三方数据服务的返回转成下面统一结构，设置对应环境变量即可，无需改代码：

```json
[
  {
    "product_id": "SKU123",
    "title": "商品标题",
    "price": 129.9,
    "sales": 3200,
    "sales_text": "已拼3200件",
    "shop_name": "店铺名",
    "rank": 1,
    "url": "https://...",
    "image": "https://..."
  }
]
```
支持 `{"items":[...]}` 包裹格式。环境变量：
`SHOPMONITOR_PDD_RANK_URL` / `SHOPMONITOR_DOUYIN_RANK_URL` / `SHOPMONITOR_TAOBAO_RANK_URL` / `SHOPMONITOR_SHOPEE_RANK_URL` / `SHOPMONITOR_AMAZON_RANK_URL` / `SHOPMONITOR_ALIEXPRESS_RANK_URL`。

## 官方开放平台适配器（2026-08-09 已内置，填凭证即用）

已内置 9 个官方开放平台适配器（5 国内 + 4 跨境），凭证填好后自动走官方 API，未填自动降级演示数据（不报错）：

| 适配器 key | 平台 | 接口 | 需要的配置项 | 说明 |
|---|---|---|---|---|
| douyin_mall | 抖店（抖音商城） | op.jinritemai.com `product.list` | DOUYIN_MALL_APP_ID / DOUYIN_MALL_SECRET | 需企业认证；部分接口可加 DOUYIN_MALL_ACCESS_TOKEN |
| taobao_open | 淘宝开放平台 | eco.taobao.com `taobao.tbk.dg.material.optional` | TAOBAO_APP_KEY / TAOBAO_APP_SECRET | 需开通淘宝客权限；部分账号需 TAOBAO_ADZONE_ID |
| pdd_open | 拼多多开放平台 | gw-api.pinduoduo.com `pdd.ddk.goods.search` | PDD_CLIENT_ID / PDD_CLIENT_SECRET | 多多客商品搜索，个人日 2000 次 |
| alibaba_open | 1688 开放平台 | gw.api.1688.com `alibaba.product.search` | ALIBABA_APP_KEY / ALIBABA_APP_SECRET + ALIBABA_ACCESS_TOKEN | 找源头工厂货源；需授权 token |
| kuaishou_open | 快手电商开放平台 | openapi.kwaixiaodian.com `open.goods.list` | KUAISHOU_APP_KEY / KUAISHOU_APP_SECRET + KUAISHOU_ACCESS_TOKEN | 需授权 token || tiktok_shop | TikTok Shop | open-api.tiktokglobalshop.com `product/202309/products/search` | TIKTOK_SHOP_APP_KEY / TIKTOK_SHOP_APP_SECRET + TIKTOK_SHOP_ACCESS_TOKEN | 商家授权后搜索/监控店铺商品；可选 SHOP_CIPHER/SHOP_ID |
| amazon_open | Amazon PA-API 5.0 | webservices.amazon.com `paapi5/searchitems` | AMAZON_ACCESS_KEY / AMAZON_SECRET_KEY / AMAZON_PARTNER_TAG | AWS SigV4 签名；Region 可选 us-east-1/eu-west-1/us-west-2 |
| shopee_open | Shopee 开放平台 v2 | partner.shopeemobile.com `product/get_item_list` + `get_item_base_info` | SHOPEE_PARTNER_ID / SHOPEE_PARTNER_KEY / SHOPEE_ACCESS_TOKEN / SHOPEE_SHOP_ID | 店铺在售商品监控（竞品店铺） |
| aliexpress_open | AliExpress 联盟 | api-sg.aliexpress.com `aliexpress.affiliate.product.query` | ALIEXPRESS_OPEN_APP_KEY / ALIEXPRESS_OPEN_APP_SECRET + ALIEXPRESS_OPEN_ACCESS_TOKEN | TOP-MD5 签名；默认销量降序、USD |

所有凭证在「接口文档 → 配置中心 → 官方开放平台凭证（国内 / 跨境）」在线保存即生效（自动重启）。
官方接口多为商家/企业资质（TikTok/Shopee/AliExpress 需商家或联盟授权，Amazon 需 AWS+联盟），个人阶段建议：**UUMit 免费数据（大盘）+ 自定义 JSON（榜单）+ 官方适配器（等资质/等申请）** 三线并行。

## 建议
- **第一步（已就绪）**：`mock` 演示数据 + UUMit 免费电商数据（大盘数据：淘宝/京东平台对比、经营概览、销售趋势）→ 直接可用于 UUMit 上架演示和本地跑通全流程。
- **第二步（可选）**：申请 1 个官方开放平台 API（推荐京东联盟）点亮"京东商品榜单"；不申请也不影响，京东平台维度真实数据已由 UUMit 免费大盘提供。
- **第三步**：逐步接入其余平台，并把"选品监控 Skill"上架 UUMit 技能市场。


## 已点亮的真实数据源（快照）
- **UUMit 热搜选词（免费，0 扣费）**：`淘宝联想词`（选词工具）、`抖音获取前十热搜`（实时热搜标题/热度/链接）、`百度热搜`（实时/小说/电影/电视剧/汽车/游戏 6 类）。面板「热搜 · 选词」三栏展示；支持导出热搜选词报告（Markdown/CSV）。无需任何平台授权。
- **UUMit 大盘数据（免费，0 扣费）**：`统计各电商平台商品表现`（淘宝/京东真实平台维度数据 + 均价倍数派生）、`查询电商订单用户经营概览`（10 项指标卡：订单/用户/成交额/客单价/销量/商品/类目/品牌/履约/发货率）、`分析电商销售额销量时间变化`（按月趋势，日期范围真实生效，按季/年为本地聚合，残月自动剔除）。面板「大盘数据」「销售趋势」即真实数据；支持导出 Markdown/CSV 报告（`/api/v1/uumit/报告`），可直接作为知识商店报告模板物料。无需任何平台授权。
- **拼多多**：已接入 `data/拼多多榜-数据源.json`（来自 GitHub lucky-pdd 的拼多多真实收藏商品，jsdelivr CDN 抓取快照，3 条：华为 Mate XTs 等）。仅演示真实数据链路，规模化请接官方/第三方数据。
  - 刷新方法：重新运行 `tools/refresh_pdd_source.py`（或直接换 `SHOPMONITOR_PDD_RANK_URL` 指向其它 JSON 接口/文件）。
