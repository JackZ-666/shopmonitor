# ShopMonitor API 文档（供 UUMit 数据广场/能力上架使用）

## 接口中文名速查表

| 中文名 | 中文路径 | 英文路径（兼容） |
|---|---|---|
| 平台列表 | `GET /api/v1/平台列表` | `GET /api/v1/platforms` |
| 拉取榜单/热卖 | `GET /api/v1/榜单/{平台}` | `GET /api/v1/rank/{platform}` |
| 关键词搜索 | `GET /api/v1/搜索/{平台}` | `GET /api/v1/search/{platform}` |
| 商品详情 | `GET /api/v1/商品/{平台}/{商品ID}` | `GET /api/v1/product/{platform}/{product_id}` |
| 价格/销量/评价历史 | `GET /api/v1/商品/{平台}/{商品ID}/历史` | `GET /api/v1/product/{platform}/{product_id}/history` |
| 涨跌分析 | `GET /api/v1/商品/{平台}/{商品ID}/涨跌` | `GET /api/v1/product/{platform}/{product_id}/change` |
| 选品对比表 | `GET /api/v1/报告/对比` | `GET /api/v1/report/compare` |
| UUMit 账户状态 | `GET /api/v1/uumit/状态` | `GET /api/v1/uumit/status` |
| 发现免费数据能力 | `GET /api/v1/uumit/免费数据` | `GET /api/v1/uumit/free-data` |
| 数据 API 详情 | `GET /api/v1/uumit/数据/{api_id}/详情` | `GET /api/v1/uumit/data/{api_id}/detail` |
| 调用免费数据 API | `POST /api/v1/uumit/数据/{api_id}/调用` | `POST /api/v1/uumit/data/{api_id}/call` |

> 中文路径与英文路径完全等价，英文路径用于程序/Agent 自动调用，中文路径方便人直接查看和演示。



服务地址：本地启动后默认 `http://127.0.0.1:8000`，交互文档 `/docs`，OpenAPI JSON `/openapi.json`。

## 一、平台与榜单

### 列出所有平台
```
GET /api/v1/platforms
```
返回每个平台的：platform / name / regions（国内|跨境）/ availability / supports_search / default_category / categories。

### 拉取榜单
```
GET /api/v1/rank/{platform}?category=数码&limit=20&fresh=false
```
- `platform`：jd / pdd / douyin / taobao / shopee / amazon / aliexpress / mock
- `fresh=true` 强制刷新（默认 10 分钟内走缓存）
- 真实采集失败自动降级演示数据：响应 `source=mock`、`degraded=true` 会明确标注
- 每次抓取会把商品快照 + 价格/销量写入 SQLite 历史

示例：
```bash
curl "http://127.0.0.1:8000/api/v1/rank/jd?category=手机&limit=10"
curl "http://127.0.0.1:8000/api/v1/rank/mock?category=数码&limit=5"
```

### 关键词搜索
```
GET /api/v1/search/{platform}?keyword=蓝牙耳机&limit=20
```
仅 `supports_search=true` 的平台可用。

## 二、商品与历史

### 商品详情（快照）
```
GET /api/v1/product/{platform}/{product_id}
```

### 价格/销量/评价历史
```
GET /api/v1/product/{platform}/{product_id}/history?limit=30
```
返回按时间倒序的 `price` / `sales` / `rating` / `review_count` 记录，用于监控降价、销量与评价趋势。

### 涨跌分析（价格/销量/评价变化）
```
GET /api/v1/product/{platform}/{product_id}/change
```
取最近两次抓取对比，返回 `price_change` / `price_change_pct` / `sales_change` / `review_change` / `direction`（up/down/flat）与一句话 `note`（如“降价 15.00；销量↑ 120”）。

## 三、选品对比报告

### 生成对比表（md / csv / xlsx）
```
GET /api/v1/report/compare?platform=mock&product_ids=demo-数码-0001,demo-数码-0002&fmt=md
```
- `fmt`：`md`（默认）| `csv` | `xlsx`
- 对比表字段（14 列）：平台 / 商品ID / 标题 / 价格 / 原价 / 促销 / 库存 / 销量 / 评分 / 评论数 / 店铺 / 店铺评分 / 排名 / 链接

## 四、UUMit 免费数据源（不扣费）

### 账户状态（只读）
```
GET /api/v1/uumit/status
```
返回 UUMit 钱包余额与星火计划 AI 额度汇总（敏感字段已剔除）。

### 发现免费电商数据能力（price_ut=0）
```
GET /api/v1/uumit/free-data?intent=电商商品销量与价格数据&top=10
```
通过 UUMit `smart-invoke mode=preview`（免费）发现可用的免费数据 API，返回 api_id / 名称 / 说明 / 入参 schema。

### 数据 API 详情
```
GET /api/v1/uumit/data/{api_id}/detail
```

### 调用免费数据 API（仅免费，付费接口拒绝）
```
POST /api/v1/uumit/data/{api_id}/call
Content-Type: application/json
{"grain":"month","dateFrom":"2024-01-01","dateTo":"2024-03-31"}
```
- 只自动调用 `price_ut=0` 的接口；付费接口返回 `status=needs_confirmation`，绝不静默扣费。
- 实测示例（2026-08-06）：`分析电商销售额销量时间变化 API`（api_id=56838770-5c57-4d1b-80c7-93ed61b57f7a）免费调用成功，返回 2024 全年月度 订单数/成交额/客单价。

## 五、说明
- 认证：本 API 面向本地/UUMit 内网使用，暂不做外部鉴权；对外部署时请在反向代理层加 API Key。
- 数据合规：仅采集公开可见数据，控制频率（单平台限流 2-3 秒），不碰登录后/付费数据；各平台官方接口见 `PLATFORM_STATUS.md`。

## 六、定时监控（P0）

| 中文名 | 中文路径 | 英文路径 |
|---|---|---|
| 监控状态 | `GET /api/v1/监控/状态` | `GET /api/v1/monitor/status` |
| 关注列表 | `GET /api/v1/监控/关注列表` | `GET /api/v1/monitor/watches` |
| 新增关注 | `POST /api/v1/监控/关注` | `POST /api/v1/monitor/watches` |
| 删除关注 | `DELETE /api/v1/监控/关注/{id}` | `DELETE /api/v1/monitor/watches/{id}` |
| 启停关注 | `POST /api/v1/监控/关注/{id}/开关` | `POST /api/v1/monitor/watches/{id}/toggle` |
| 立即巡检 | `POST /api/v1/监控/运行` | `POST /api/v1/monitor/run` |
| 告警列表 | `GET /api/v1/监控/告警` | `GET /api/v1/monitor/alerts` |
| 标记已读 | `POST /api/v1/监控/告警/已读` | `POST /api/v1/monitor/alerts/read` |

**告警规则**：降价（≥3% 或 ≥5 元）、库存变缺货/预售、评分下滑（≥0.3）、评论激增（≥50 条）、销量激增（≥100）、排名变动（≥3）、新进 Top-N。
**推送**：默认入库 + 写 `data/alerts.jsonl`；配置 `SHOPMONITOR_WEBHOOK_URL`（企业微信/钉钉/飞书）后自动推送。
**示例**
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/监控/关注" -H "Content-Type: application/json" -d '{"platform":"mock","category":"数码","top_n":5}'
curl -X POST "http://127.0.0.1:8000/api/v1/监控/运行"
curl "http://127.0.0.1:8000/api/v1/监控/告警?unread=true"
```
