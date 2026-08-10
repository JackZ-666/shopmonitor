# 方案 E：无服务器数据包（GitHub Actions 免费自动生成）



> 零服务器、零成本：用 GitHub 免费 Actions 每天自动生成 7 大平台数据 JSON，

> 推到 GitHub Pages（免费静态托管），客户在配置中心填一次地址即可。



---



## 一、原理



```

GitHub Actions（每天 02:00 自动跑）           GitHub Pages（免费托管）

┌─────────────────────────────┐            ┌─────────────────────────┐

│ 有官方凭证 -> 调官方 API 真实数据 │  push      │ https://你.github.io/仓库/ │

│ 无凭证     -> 预置数据兜底      │──────────▶│   data/jd.json …         │

└─────────────────────────────┘            └────────────┬────────────┘

                                                         │ 客户填这个地址

                                        ┌────────────────▼────────────┐

                                        │ 客户面板：配置中心 → 填数据包地址 │

                                        │ → 一键填入 7 平台数据源          │

                                        └─────────────────────────────┘

```



## 二、你要做的（一次性，约 10 分钟，免费）



1. 注册 GitHub：https://github.com （免费）

2. 新建仓库（Public），把本项目上传（`git init` → push，或网页上传）

   - 项目里已含 `.github/workflows/data-pack.yml`（工作流）和 `tools/gen_data_pack.py`（生成器）

3. 可选：把官方凭证存成仓库 Secrets（Settings → Secrets and variables → Actions）。按「好申请→难申请」排序：

   - **`PDD_CLIENT_ID` / `PDD_CLIENT_SECRET`（拼多多多多客）**：个人可注册，无需流量证明，最推荐先做

   - **`ALIEXPRESS_OPEN_APP_KEY` / `ALIEXPRESS_OPEN_APP_SECRET` / `ALIEXPRESS_OPEN_ACCESS_TOKEN`（AliExpress 联盟）**：个人可注册推广者，无需流量证明

   - `JD_UNION_APP_KEY` / `JD_UNION_SECRET_KEY`（京东联盟）：个人可注册，但**需开通 goods.query 接口权限**（部分账号要求提供推广网站/流量证明，审核通过才生效）

   - `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY` / `AMAZON_PARTNER_TAG`（Amazon PA-API）：免费，但 Associates 注册需提供有效网站，个人通过率低

   - 有凭证的平台每天生成真实数据；没填的用预置数据。

4. 打开仓库 Settings → Pages → Source 选 `gh-pages`（工作流第一次跑完会自动建该分支）

5. 手动触发一次：仓库 Actions → 数据包 → Run workflow

6. 验证：访问 `https://你的用户名.github.io/仓库名/data/jd.json` 能看到 JSON 即成功



## 三、给客户



- 数据包地址（base）：`https://你的用户名.github.io/仓库名`

- 客户操作：面板 → 配置中心 → 粘贴 base 地址 → 点「一键填数据包」→ 保存 → 重启

  → 7 平台榜单显示数据包数据（有官方凭证的平台为真实数据）

- 每天自动更新（无需你做任何事）



## 四、注意



- GitHub 仓库要 Public 才能用 Pages；数据是公开的（榜单类公开数据可接受）。

- 免费 Actions 每月 2000 分钟，每天跑一次足够。

- 想"更私密/更大数据"再升级方案 B（Oracle 免费云）或 A（本机穿透）。

