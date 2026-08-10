# ShopMonitor — 全平台电商选品/竞品监控套件（UUMit 上架用）

跨平台电商数据采集 + 多维监控（价格/销量/排名/评价/库存/促销/店铺）+ 涨跌分析 + 选品对比报告 + UUMit 免费数据源，做成可上架 UUMit 的"数据/API + Skill"组合产品。

**定时监控 + 告警**：关注榜单/关键词/单品，周期巡检自动比对，产出 降价/缺货/评分下滑/评论激增/销量激增/排名变动 告警，可推送企业微信/钉钉/飞书 Webhook（`SHOPMONITOR_WEBHOOK_URL`）。

**监控维度（按主流电商运营需求设计）**：价格（含促销/原价）、销量与趋势、榜单/搜索排名、评分与评论数、库存状态、店铺评分、品牌/类目、利润估算（模板内建）。详见 [docs/MONITORING_GUIDE.md](docs/MONITORING_GUIDE.md)。

## 第一版交付

- 全中文看板（http://127.0.0.1:8010，深色/浅色 + 数据大屏 http://127.0.0.1:8010/大屏）、**模块化视图 + 快捷指令（Ctrl+K）+ 应用图标 + 可选访问口令**、今日焦点概览、定时监控告警、日报/周报/月报、16 列选品对比表、毛利估算器（整套+自定义模板）、蓝海选词、榜单趋势、价格带分析（含跨平台对比）、选品库、竞品店铺监控、1688 找货源、UUMit 离线样例兜底（无技能也能看到大盘/热搜）、商品详情预估月销/GMV、今日变动榜、UUMit 免费数据（大盘 + 平台对比 + 销售趋势 + 抖音/百度热搜 + 淘宝选词 + 报告导出 + 价格历史 + 排名趋势 + AI 选品分析）。
- 交付清单见 [docs/DELIVERABLES.md](docs/DELIVERABLES.md)；上架文案见 [docs/UUMIT_LISTING.md](docs/UUMIT_LISTING.md)。

## 支持平台

| 国内 | 跨境 | 平台数据 |
|---|---|---|
| 京东 / 拼多多 / 抖音电商 / 淘宝 | Shopee / Amazon / AliExpress | UUMit 免费电商数据（price_ut=0） |

> 真实平台采集受反爬限制，未配置凭证时自动降级为演示数据（响应 `degraded=true`），详见 [docs/PLATFORM_STATUS.md](docs/PLATFORM_STATUS.md)。

## 快速开始

## 一键启动（Windows）

1. 首次：双击 **安装依赖.bat**（自动装依赖 + 环境自检）
2. 日常：双击 **启动.bat** → 自动启动并打开接口文档
3. 停止：双击 **停止.bat**；管理：双击 **管理菜单.bat**（中文菜单）
4. 配置：复制 `配置文件-示例.env` 为 `配置文件.env` 修改后重启生效

命令行等价：
```bash
pip install -r requirements.txt
python tools/launcher.py start     # 或 python run_api.py
python tools/launcher.py status    # 状态/告警
python tools/launcher.py menu      # 中文管理菜单
curl "http://127.0.0.1:8010/api/v1/榜单/mock?category=数码&limit=5"
curl "http://127.0.0.1:8010/api/v1/uumit/状态"          # UUMit 钱包（只读）
curl "http://127.0.0.1:8010/api/v1/uumit/免费数据"       # 发现 UUMit 免费数据 API
```
> 端口默认 8010（可改配置文件）。无服务器数据包方案见 [docs/方案E-无服务器数据包.md](docs/方案E-无服务器数据包.md)。

## 主要接口

| 接口 | 说明 |
|---|---|
| `GET /api/v1/platforms` | 平台列表与可用性 |
| `GET /api/v1/rank/{platform}?category=&limit=` | 榜单/热卖（自动缓存 + 降级） |
| `GET /api/v1/search/{platform}?keyword=` | 关键词搜索 |
| `GET /api/v1/product/{platform}/{id}` | 商品快照 |
| `GET /api/v1/product/{platform}/{id}/history` | 价格/销量/评分/评论数历史（SQLite 累积） |
| `GET /api/v1/product/{platform}/{id}/change` | 涨跌分析（降价/销量/评价变化） |
| `POST /api/v1/监控/关注` | 新增监控关注（榜单/关键词/单品） |
| `POST /api/v1/监控/运行` | 立即巡检一轮 |
| `GET /api/v1/监控/告警` | 降价/缺货/评价/销量告警 |
| `GET /api/v1/report/compare?platform=&product_ids=&fmt=md|csv|xlsx` | 选品对比表（16 列，含预估毛利/毛利率，可传成本占比/运费/ACOS） |
| `GET /api/v1/uumit/status` | UUMit 账户（只读） |
| `GET /api/v1/uumit/free-data?intent=` | 发现 UUMit 免费数据能力（不扣费） |
| `POST /api/v1/uumit/data/{api_id}/call` | 调用免费数据 API（付费接口拒绝） |
| `GET /api/v1/uumit/大盘` | 大盘数据：账户 + 平台对比 + 概览 + 趋势（真实免费） |
| `GET /api/v1/uumit/平台对比` | 淘宝/京东平台维度商品数、均价、销量、评分 |
| `GET /api/v1/uumit/经营概览` | 订单、用户、成交额、客单价等大盘指标 |
| `GET /api/v1/uumit/趋势?grain=&date_from=&date_to=` | 销售趋势（日期真实生效，季/年本地聚合，环比+残月标注） |
| `GET /api/v1/uumit/报告?fmt=md|csv` | 导出大盘报告（Markdown/CSV，可当知识商店物料） |
| `GET /api/v1/uumit/联想词?keyword=` | 淘宝联想词（选词工具，真实免费数据） |
| `GET /api/v1/uumit/热搜` | 抖音实时热搜前 10（标题/热度/链接，真实免费数据） |
| `GET /api/v1/uumit/百度热搜?type=realtime` | 百度热搜（实时/小说/电影/电视剧/汽车/游戏） |
| `GET /api/v1/uumit/热搜报告?fmt=md|csv&keyword=` | 导出热搜选词报告（抖音+百度+联想词） |
| `POST/GET /api/v1/监控/日报` | 生成/查看今日日报（大盘+热搜+告警+关注商品快照含预估毛利；`fmt=pdf` 导出；推送 Webhook/邮件/Telegram） |
| `GET /api/v1/report/compare?fmt=pdf` | 选品对比表 PDF 导出；`GET /api/v1/tools/filter?fmt=pdf` 选品毛利表 PDF 导出 |
| `POST/GET /api/v1/监控/周期报告?period=week|month` | 生成/查看周报/月报（告警统计+商品动态+热搜+大盘） |
| `GET /api/v1/工具/榜单趋势?platform=&category=&days=` | 类目榜单历史趋势（每日商品数/均价/新品，自动积累） |
| `GET /api/v1/工具/价格带分析?platform=&category=` | 价格带分析（价格分布/平均销量/建议定价带） |
| `GET /api/v1/工具/跨平台价格带?category=&platforms=` | 跨平台价格带对比（同关键词多平台比价，标出哪边好卖） |
| `GET /api/v1/工具/竞争度分析?platform=&category=` | 类目竞争度（卖家数/头部集中度/价格离散度 → 蓝海/红海指数） |
| `GET /api/v1/工具/竞品动态?platform=&days=` | 竞品店动态时间线（新品上榜/降价/涨价/销量飙升/排名变动） |
| `POST /api/v1/配置/启用预置数据` | 一键启用 7 平台预置数据（免配置） |
| `POST /api/v1/配置/填数据包` | 一键填 GitHub Pages 数据包（7 平台数据源 URL，方案E 无服务器，见 docs/方案E-无服务器数据包.md） |
| `GET /api/v1/监控/排名趋势?watch_id=` | 关注项排名/价格/销量历史序列（趋势图） |
| `POST /api/v1/ai/选品分析?keyword=` | AI 选品分析（大盘+热搜+联想词 -> 大模型建议，OpenAI 兼容） |
| `GET /api/v1/ai/状态` | AI 配置状态（不返回 Key） |
| `GET /api/v1/工具/毛利估算?sale_price=&cost=` | 毛利估算器（毛利/毛利率/ROI；整套模板一键带入 + 结算币种+实时汇率+运营模式+FBA 分档+履约/仓储/长期仓储/移除/收付费/汇损/打包/ACOS/关税/退货/固定费，费用按 平台/物流/税务资金 分类展示） |
| `GET /api/v1/监控/变动榜` | 今日变动榜（降价/涨价/销量飙升，对标 Keepa） |
| `GET /api/v1/工具/汇率` | 跨境结算币种与人民币汇率（实时，失败用内置快照；含平台→币种对照） |
| `GET /api/v1/工具/运营模式` | 各平台运营/发货模式预设（Amazon FBA/FBM + 6 档 FBA 履行费分档、平台物流/自发货/海外仓、一件代发等 + 8 类类目 ACOS 预设） |
| `GET /api/v1/工具/筛选?platform=&price_max=&min_sales=` | 潜力商品筛选（价格/销量/评分/排名等，按潜力分排序；支持成本/运费/ACOS/关税/退货 预估毛利、最低毛利过滤；`fmt=xlsx` 一键导出选品毛利表） |
| `GET /api/v1/监控/关注总览` | 关注商品总览（各关注商品最新价格/销量/排名/库存） |
| `GET /api/v1/uumit/热搜趋势?platform=douyin&days=7` | 热搜词热度趋势（自动积累快照） |
| `POST /api/v1/监控/批量导入` | 批量导入商品链接/ID 添加监控（自动识别平台） |
| `GET /api/v1/配置/状态` | 配置状态总览（各数据源/AI/推送是否已配置，不返回密钥） |
| `GET /api/v1/配置/数据源模板` | 下载自定义 JSON 数据源模板 |
| `GET /api/v1/监控/新品榜` | 新品上榜（竞品上新监控，榜单级） |
| `GET /api/v1/套餐/状态` | 订阅套餐状态（free/pro/enterprise + 限额） |
| `GET /api/v1/uumit/报告?lang=en` 等 | 英文报告（大盘/热搜/对比，跨境卖家） |
| `/接口文档` | 自定义中文接口文档（快速开始 + 在线配置中心 + 电商配置引导 + 颗粒化接口目录） |
| `GET/POST /api/v1/配置/可配置项、保存` | 在线配置：网页直接改 48 项（AI/京东联盟/官方凭证国内+跨境：抖店/淘宝/拼多多/1688/快手/TikTok Shop/Amazon/Shopee/AliExpress/Cookie/JSON数据源/Webhook/套餐），保存后自动重启生效 |
| `POST /api/v1/配置/测试数据源、测试AI、测试Webhook` | 保存前先验证数据源/AI/推送是否可用 |

完整文档见 [docs/OPENAPI.md](docs/OPENAPI.md)，交互文档启动后见 `/docs`。

## 打包分享（给朋友免安装使用）

- **绿色便携版（推荐，免安装免 Python）**：运行 `python tools/build_share_pkg.py` 生成
  `dist/ShopMonitor分享版/`（内置 Python 3.12 + 全部依赖，约 22MB zip）。
  朋友使用：解压 → 双击「创建桌面快捷方式.bat」→ 桌面出现「ShopMonitor 选品监控」图标 → 双击启动
  （或直接双击「启动-选品监控.bat」）。
- **正式安装包（可选）**：装好 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 后，
  双击 `打包/编译安装包.bat` 生成 `dist/ShopMonitor安装程序.exe`，安装后自动创建桌面快捷方式。
- 数据全部存在本机 `data/` 目录，UUMit 免费数据需本机装了 uumit-agent 技能才可用（没有不影响其它功能）。

## 测试与工具

```bash
python -m pytest tests -v                # 174 项测试（解析 + API 端到端 + UUMit 集成 + 大盘/报告/热搜/日报/周报月报/排名/主题大屏/AI(含无Key规则兜底)/毛利(带标签+整套模板+自定义模板+外贸费用)/汇率/运营模式/变动榜/筛选(含预估毛利+导出Excel/PDF)/对比(含PDF)/日报(含PDF)/毛利概览/蓝海选词/选品库/店铺监控/1688找货源/榜单趋势/价格带分析/类目竞争度分析/竞品动态/商品详情(预估毛利+月销/GMV)/离线样例兜底/访问口令/免配置预置数据(7平台一键启用)/无服务器数据包(GitHub Actions)/多通道通知(Webhook+邮件+Telegram，含凭据校验)/PDF导出/快捷启动/总览/批量导入/热搜趋势/配置状态/新品榜/套餐/英文/文档页/在线配置）
python tools/probe_platforms.py          # 真实平台连通性探测（联网）
python tools/probe_uumit.py              # UUMit 账户 + 免费数据探测（联网）
python tools/make_assets.py              # 生成选品对比表模板/示例（assets/）
```

## 点亮真实平台数据（三种方式）

1. **官方开放平台 API**（推荐）：京东联盟 / 淘宝开放平台 / 拼多多开放平台 / 抖音电商开放平台 / 1688 / 快手 / TikTok Shop / Amazon PA-API / Shopee Open Platform / AliExpress 联盟（均已内置适配器，填凭证即用），写采集脚本转成统一 JSON。
2. **登录 Cookie**：淘宝等设 `TAOBAO_COOKIE`。
3. **自定义 JSON 数据源**：任意接口转成统一结构（`product_id/title/price/sales/shop_name/rank/url`），设 `SHOPMONITOR_<平台>_RANK_URL` 即可，无需改代码。

详见 [docs/PLATFORM_STATUS.md](docs/PLATFORM_STATUS.md)。

## UUMit 上架

- `uumit/SKILL.md` + `uumit/scripts/sku_monitor.py`：选品监控 Skill 骨架（技能市场）
- `docs/OPENAPI.md`：数据接口文档（数据广场/能力上架）
- `assets/`：选品对比表模板与示例（知识商店）
- 免费数据源：已接入 uumit-agent 技能，自动调用 UUMit 数据广场免费接口（只调 price_ut=0，绝不自动扣费）

上架流程（用 uumit-publisher）：
```bash
node C:/Users/HP/.codex/skills/uumit-publisher/scripts/publisher.js upload --file uumit/SKILL.md
node C:/Users/HP/.codex/skills/uumit-publisher/scripts/publisher.js batch-publish --dry-run
```

## 合规声明

- 只采集公开可见数据，控制抓取频率（内置限流），不碰登录后/付费数据；使用官方 API 时遵守其服务条款。
- UUMit 侧：只自动调用免费接口；付费/高风险操作一律先返回确认，绝不静默扣费。

## 目录结构

```
启动.bat / 停止.bat / 管理菜单.bat / 安装依赖.bat   # 一键启动与运维
配置文件-示例.env                                 # 配置模板（复制为 配置文件.env 生效）
Dockerfile / docker-compose.yml                   # 云部署
shopmonitor/          # 核心包（适配器/缓存/模型/API/监控引擎）
  collectors/         # 平台适配器（jd/pdd/douyin/taobao/shopee/amazon/aliexpress/mock）
  api/main.py         # FastAPI 入口（中英双路径）
  monitor.py          # 定时监控 + 告警引擎
  uumit_feed.py       # UUMit 免费数据源集成（只调 price_ut=0 接口）
  uumit_data.py       # 大盘数据：平台对比/经营概览/销售趋势归一化
assets/               # 选品对比表模板/示例/封面
docs/                 # 接口文档 + 平台状态 + 监控指南 + 部署文档
uumit/                # UUMit 上架 Skill 骨架
tools/                # launcher/monitor_cli/探测/资产生成
tests/                # pytest 测试
run_api.py            # 服务入口
```