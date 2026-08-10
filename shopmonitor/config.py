"""全局配置：路径、请求参数、各平台凭证、监控与告警（全部可用环境变量或 配置文件.env 覆盖）。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """极简 .env 加载：KEY=VALUE，支持 # 注释与引号；已存在的环境变量不覆盖。"""
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        # 支持行尾注释：`KEY=值 # 说明`（值里含 # 时请用引号包住，否则按注释截断）
        v = v.split(" #", 1)[0].split("\t#", 1)[0].strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


# 优先加载项目根目录的 配置文件.env（其次 .env）
_load_dotenv(BASE_DIR / "配置文件.env")
_load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.environ.get("SHOPMONITOR_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("SHOPMONITOR_DB_PATH", str(DATA_DIR / "shopmonitor.db")))

# ---- 服务端口 ----
HOST = os.environ.get("SHOPMONITOR_HOST", "127.0.0.1")
# 面板访问口令（可选）：设置后需输入口令才能打开面板/大屏/接口文档；留空=不启用
SHOPMONITOR_PASSWORD = os.environ.get("SHOPMONITOR_PASSWORD", "")
PORT = int(os.environ.get("SHOPMONITOR_PORT", "8010"))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = float(os.environ.get("SHOPMONITOR_TIMEOUT", "10"))

# 榜单缓存 TTL（秒），默认 10 分钟，避免频繁打源站
DEFAULT_RANK_TTL = int(os.environ.get("SHOPMONITOR_RANK_TTL", "600"))
# 单平台最小请求间隔（秒）
DEFAULT_RATE_LIMIT_SEC = float(os.environ.get("SHOPMONITOR_RATE_LIMIT", "2.0"))

# 真实采集失败时是否自动降级到演示数据（默认开，方便试跑）
ALLOW_MOCK_FALLBACK = os.environ.get("SHOPMONITOR_ALLOW_MOCK", "1") == "1"

# ---- 需要凭证的平台（可选配置，不配则提示需要配置） ----
TAOBAO_COOKIE = os.environ.get("TAOBAO_COOKIE", "")
SHOPEE_COOKIE = os.environ.get("SHOPEE_COOKIE", "")

# 反爬较强平台的"自定义数据源"入口：拿到官方/付费接口后，把返回 JSON 的地址配到这里即可无缝接入。
PDD_RANK_URL = os.environ.get("SHOPMONITOR_PDD_RANK_URL", "")
DOUYIN_RANK_URL = os.environ.get("SHOPMONITOR_DOUYIN_RANK_URL", "")
JD_RANK_URL = os.environ.get("SHOPMONITOR_JD_RANK_URL", "")
TAOBAO_RANK_URL = os.environ.get("SHOPMONITOR_TAOBAO_RANK_URL", "")
SHOPEE_RANK_URL = os.environ.get("SHOPMONITOR_SHOPEE_RANK_URL", "")
AMAZON_RANK_URL = os.environ.get("SHOPMONITOR_AMAZON_RANK_URL", "")
ALIEXPRESS_RANK_URL = os.environ.get("SHOPMONITOR_ALIEXPRESS_RANK_URL", "")

# ---- 官方开放平台凭证（抖音商城/淘宝/拼多多/1688/快手，接入官方 API 用） ----
DOUYIN_MALL_APP_ID = os.environ.get("DOUYIN_MALL_APP_ID", "")
DOUYIN_MALL_SECRET = os.environ.get("DOUYIN_MALL_SECRET", "")
TAOBAO_APP_KEY = os.environ.get("TAOBAO_APP_KEY", "")
TAOBAO_APP_SECRET = os.environ.get("TAOBAO_APP_SECRET", "")
PDD_CLIENT_ID = os.environ.get("PDD_CLIENT_ID", "")
PDD_CLIENT_SECRET = os.environ.get("PDD_CLIENT_SECRET", "")
ALIBABA_APP_KEY = os.environ.get("ALIBABA_APP_KEY", "")
ALIBABA_APP_SECRET = os.environ.get("ALIBABA_APP_SECRET", "")
KUAISHOU_APP_KEY = os.environ.get("KUAISHOU_APP_KEY", "")
KUAISHOU_APP_SECRET = os.environ.get("KUAISHOU_APP_SECRET", "")
# 可选：官方开放平台已获取的 Token / 扩展参数（部分平台接口需要，没有则自动降级提示）
DOUYIN_MALL_ACCESS_TOKEN = os.environ.get("DOUYIN_MALL_ACCESS_TOKEN", "")
ALIBABA_ACCESS_TOKEN = os.environ.get("ALIBABA_ACCESS_TOKEN", "")
KUAISHOU_ACCESS_TOKEN = os.environ.get("KUAISHOU_ACCESS_TOKEN", "")
TAOBAO_ADZONE_ID = os.environ.get("TAOBAO_ADZONE_ID", "")   # 淘宝客推广位ID（物料接口部分账号必填）

# ---- 官方开放平台凭证（跨境：TikTok Shop / Amazon PA-API / Shopee / AliExpress） ----
TIKTOK_SHOP_APP_KEY = os.environ.get("TIKTOK_SHOP_APP_KEY", "")
TIKTOK_SHOP_APP_SECRET = os.environ.get("TIKTOK_SHOP_APP_SECRET", "")
TIKTOK_SHOP_ACCESS_TOKEN = os.environ.get("TIKTOK_SHOP_ACCESS_TOKEN", "")
TIKTOK_SHOP_SHOP_CIPHER = os.environ.get("TIKTOK_SHOP_SHOP_CIPHER", "")
TIKTOK_SHOP_SHOP_ID = os.environ.get("TIKTOK_SHOP_SHOP_ID", "")
AMAZON_ACCESS_KEY = os.environ.get("AMAZON_ACCESS_KEY", "")
AMAZON_SECRET_KEY = os.environ.get("AMAZON_SECRET_KEY", "")
AMAZON_PARTNER_TAG = os.environ.get("AMAZON_PARTNER_TAG", "")
AMAZON_PARTNER_TYPE = os.environ.get("AMAZON_PARTNER_TYPE", "Associates")
AMAZON_REGION = os.environ.get("AMAZON_REGION", "us-east-1")
AMAZON_HOST = os.environ.get("AMAZON_HOST", "")
SHOPEE_PARTNER_ID = os.environ.get("SHOPEE_PARTNER_ID", "")
SHOPEE_PARTNER_KEY = os.environ.get("SHOPEE_PARTNER_KEY", "")
SHOPEE_ACCESS_TOKEN = os.environ.get("SHOPEE_ACCESS_TOKEN", "")
SHOPEE_SHOP_ID = os.environ.get("SHOPEE_SHOP_ID", "")
ALIEXPRESS_OPEN_APP_KEY = os.environ.get("ALIEXPRESS_OPEN_APP_KEY", "")
ALIEXPRESS_OPEN_APP_SECRET = os.environ.get("ALIEXPRESS_OPEN_APP_SECRET", "")
ALIEXPRESS_OPEN_ACCESS_TOKEN = os.environ.get("ALIEXPRESS_OPEN_ACCESS_TOKEN", "")
ALIEXPRESS_SORT = os.environ.get("ALIEXPRESS_SORT", "total_sales_des")
ALIEXPRESS_CURRENCY = os.environ.get("ALIEXPRESS_CURRENCY", "USD")
ALIEXPRESS_TRACKING_ID = os.environ.get("ALIEXPRESS_TRACKING_ID", "")

# UUMit 免费数据源集成（uumit-agent 技能目录，可留空自动探测）
UUMIT_SKILL_DIR = os.environ.get("UUMIT_SKILL_DIR", "")

# ---- 定时监控（P0） ----
MONITOR_ENABLED = os.environ.get("SHOPMONITOR_MONITOR", "1") == "1"
MONITOR_INTERVAL_SEC = int(os.environ.get("SHOPMONITOR_MONITOR_INTERVAL", "3600"))
MONITOR_TOP_N = int(os.environ.get("SHOPMONITOR_MONITOR_TOP_N", "10"))
# 告警阈值
PRICE_DROP_THRESHOLD_PCT = float(os.environ.get("SHOPMONITOR_PRICE_DROP_PCT", "3"))
PRICE_DROP_THRESHOLD_ABS = float(os.environ.get("SHOPMONITOR_PRICE_DROP_ABS", "5"))
RATING_DROP_THRESHOLD = float(os.environ.get("SHOPMONITOR_RATING_DROP", "0.3"))
REVIEW_SURGE_THRESHOLD = int(os.environ.get("SHOPMONITOR_REVIEW_SURGE", "50"))
SALES_SURGE_THRESHOLD = int(os.environ.get("SHOPMONITOR_SALES_SURGE", "100"))
RANK_CHANGE_THRESHOLD = int(os.environ.get("SHOPMONITOR_RANK_CHANGE", "3"))
# 告警推送：企业微信/钉钉/飞书 Webhook（不配置则只入库 + 写 alerts.jsonl）
ALERT_WEBHOOK_URL = os.environ.get("SHOPMONITOR_WEBHOOK_URL", "")
# 告警推送：邮件 / Telegram（可选；任配一项即多通道通知）
ALERT_EMAIL_SMTP_HOST = os.environ.get("ALERT_EMAIL_SMTP_HOST", "")
ALERT_EMAIL_SMTP_PORT = int(os.environ.get("ALERT_EMAIL_SMTP_PORT", "465"))
ALERT_EMAIL_USER = os.environ.get("ALERT_EMAIL_USER", "")
ALERT_EMAIL_PASS = os.environ.get("ALERT_EMAIL_PASS", "")
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
ALERT_TELEGRAM_BOT_TOKEN = os.environ.get("ALERT_TELEGRAM_BOT_TOKEN", "")
ALERT_TELEGRAM_CHAT_ID = os.environ.get("ALERT_TELEGRAM_CHAT_ID", "")
ALERT_JSONL_PATH = DATA_DIR / "alerts.jsonl"

# ---- AI 选品分析（OpenAI 兼容大模型 API，任选一家：豆包/智谱/通义/DeepSeek） ----
AI_LLM_API_KEY = os.environ.get("AI_LLM_API_KEY", "")
AI_LLM_BASE_URL = os.environ.get("AI_LLM_BASE_URL", "").rstrip("/")
AI_LLM_MODEL = os.environ.get("AI_LLM_MODEL", "")
# 常见默认（未配置 base_url/model 时按 key 前缀猜测）
_DEFAULT_LLM = {
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    "dashscope": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "ark": ("https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-2.0-lite-32k"),
}
def resolve_llm_endpoint() -> tuple:
    """返回 (base_url, model)；未显式配置时按 key 前缀猜测。"""
    base = AI_LLM_BASE_URL
    model = AI_LLM_MODEL
    if base and model:
        return base, model
    key = (AI_LLM_API_KEY or "").lower()
    if "zhipu" in key or "glm" in key:
        base, model = _DEFAULT_LLM["zhipu"]
    elif "sk-" in key and ("dashscope" in key or "qwen" in key or "aliyun" in key):
        base, model = _DEFAULT_LLM["dashscope"]
    elif "sk-" in key and ("deepseek" in key or "ds" in key):
        base, model = _DEFAULT_LLM["deepseek"]
    elif "ark" in key or "volc" in key or "doubao" in key:
        base, model = _DEFAULT_LLM["ark"]
    else:
        base = base or _DEFAULT_LLM["zhipu"][0]
        model = model or _DEFAULT_LLM["zhipu"][1]
    return base, model


# ---- 订阅套餐（MVP：按套餐限制功能与数量） ----
PLAN_NAME = os.environ.get("SHOPMONITOR_PLAN", "free").lower()  # free | pro | enterprise
# 各套餐限额：关注数上限 / 是否启用 AI / 是否启用英文报告
_PLANS = {
    "free": {"max_watches": 5, "ai": False, "en_report": True},
    "pro": {"max_watches": 50, "ai": True, "en_report": True},
    "enterprise": {"max_watches": 9999, "ai": True, "en_report": True},
}
PLAN_LIMITS = _PLANS.get(PLAN_NAME, _PLANS["free"])


# ---- 京东联盟开放平台（官方 API） ----
JD_UNION_APP_KEY = os.environ.get("JD_UNION_APP_KEY", "")
JD_UNION_SECRET_KEY = os.environ.get("JD_UNION_SECRET_KEY", "")
JD_UNION_ELITE_ID = os.environ.get("JD_UNION_ELITE_ID", "")   # 可选：频道ID（不配则用关键词搜）


# ---- 在线配置（接口文档页可直接改，改完自动重启生效） ----
# 允许通过 UI 修改的配置项：key -> (中文名, 分类, 是否敏感, 提示)
UI_CONFIG_SCHEMA = {
    # AI 选品
    "AI_LLM_API_KEY": ("AI Key", "ai", True, "豆包/智谱/通义/DeepSeek 任选（OpenAI 兼容），填 sk-xxx 或 ark-xxx"),
    "AI_LLM_BASE_URL": ("AI 接口地址", "ai", False, "留空自动按 Key 识别；如 https://open.bigmodel.cn/api/paas/v4"),
    "AI_LLM_MODEL": ("AI 模型", "ai", False, "留空自动按 Key 识别；豆包需填已开通模型，如 doubao-seed-2-0-lite-260215"),
    # 京东联盟
    "JD_UNION_APP_KEY": ("京东联盟 AppKey", "jd", False, "union.jd.com 开放平台应用 AppKey"),
    "JD_UNION_SECRET_KEY": ("京东联盟 SecretKey", "jd", True, "应用 SecretKey；需在后台开通 goods.query 权限"),
    "JD_UNION_ELITE_ID": ("京东联盟频道ID", "jd", False, "可选；留空用关键词搜索"),
    # 登录 Cookie
    "TAOBAO_COOKIE": ("淘宝登录 Cookie", "cookie", True, "浏览器登录淘宝后复制的 Cookie"),
    "SHOPEE_COOKIE": ("Shopee 登录 Cookie", "cookie", True, "登录 Shopee 后复制 Cookie"),
    # 自定义 JSON 数据源
    "SHOPMONITOR_JD_RANK_URL": ("京东 JSON 数据源", "json", False, "HTTP 地址或本地 json 文件路径"),
    "SHOPMONITOR_PDD_RANK_URL": ("拼多多 JSON 数据源", "json", False, "HTTP 地址或本地 json 文件路径"),
    "SHOPMONITOR_DOUYIN_RANK_URL": ("抖音 JSON 数据源", "json", False, "HTTP 地址或本地 json 文件路径"),
    "SHOPMONITOR_TAOBAO_RANK_URL": ("淘宝 JSON 数据源", "json", False, "HTTP 地址或本地 json 文件路径"),
    "SHOPMONITOR_SHOPEE_RANK_URL": ("Shopee JSON 数据源", "json", False, "HTTP 地址或本地 json 文件路径"),
    "SHOPMONITOR_AMAZON_RANK_URL": ("Amazon JSON 数据源", "json", False, "HTTP 地址或本地 json 文件路径"),
    "SHOPMONITOR_ALIEXPRESS_RANK_URL": ("AliExpress JSON 数据源", "json", False, "HTTP 地址或本地 json 文件路径"),
    # 官方开放平台凭证（接入官方 API 用）
    "DOUYIN_MALL_APP_ID": ("抖店 AppID", "official", False, "抖音商城/抖店开放平台 op.jinritemai.com 应用 AppID（需企业认证）"),
    "DOUYIN_MALL_SECRET": ("抖店 Secret", "official", True, "抖店开放平台应用 Secret"),
    "TAOBAO_APP_KEY": ("淘宝 AppKey", "official", False, "淘宝开放平台 open.taobao.com 应用 AppKey"),
    "TAOBAO_APP_SECRET": ("淘宝 AppSecret", "official", True, "淘宝开放平台应用 Secret"),
    "PDD_CLIENT_ID": ("拼多多 ClientId", "official", False, "拼多多开放平台 open.pinduoduo.com 应用 ClientId"),
    "PDD_CLIENT_SECRET": ("拼多多 ClientSecret", "official", True, "拼多多开放平台应用 ClientSecret"),
    "ALIBABA_APP_KEY": ("1688 AppKey", "official", False, "1688 开放平台 open.1688.com 应用 AppKey"),
    "ALIBABA_APP_SECRET": ("1688 AppSecret", "official", True, "1688 开放平台应用 AppSecret"),
    "KUAISHOU_APP_KEY": ("快手 AppKey", "official", False, "快手电商开放平台 open.kwaixiaodian.com 应用 AppKey"),
    "KUAISHOU_APP_SECRET": ("快手 AppSecret", "official", True, "快手电商开放平台应用 AppSecret"),
    "DOUYIN_MALL_ACCESS_TOKEN": ("抖店 AccessToken", "official", True, "可选；部分抖店接口需要商家授权 token（未填则自动降级提示）"),
    "ALIBABA_ACCESS_TOKEN": ("1688 AccessToken", "official", True, "1688 开放平台授权后获取的 access_token（必填才能调搜索）"),
    "KUAISHOU_ACCESS_TOKEN": ("快手 AccessToken", "official", True, "快手电商开放平台授权后获取的 access_token（必填才能调商品列表）"),
    "TAOBAO_ADZONE_ID": ("淘宝客推广位ID", "official", False, "可选；taobao.tbk.dg.material.optional 部分账号必填 adzone_id"),
    # 官方开放平台凭证（跨境：TikTok Shop / Amazon / Shopee / AliExpress）
    "TIKTOK_SHOP_APP_KEY": ("TikTok Shop AppKey", "official_global", False, "TikTok Shop Partner Center 应用 AppKey（商家授权后使用）"),
    "TIKTOK_SHOP_APP_SECRET": ("TikTok Shop AppSecret", "official_global", True, "TikTok Shop Partner Center 应用 AppSecret"),
    "TIKTOK_SHOP_ACCESS_TOKEN": ("TikTok Shop AccessToken", "official_global", True, "商家授权 access_token（必填才能调商品搜索）"),
    "TIKTOK_SHOP_SHOP_CIPHER": ("TikTok Shop 店铺Cipher", "official_global", False, "授权后获取的 shop_cipher（可选）"),
    "TIKTOK_SHOP_SHOP_ID": ("TikTok Shop 店铺ID", "official_global", False, "店铺 shop_id（可选）"),
    "AMAZON_ACCESS_KEY": ("Amazon AccessKey", "official_global", False, "AWS 访问密钥（PA-API 需在 AWS IAM 开通）"),
    "AMAZON_SECRET_KEY": ("Amazon SecretKey", "official_global", True, "AWS 密钥（与 AccessKey 配对）"),
    "AMAZON_PARTNER_TAG": ("Amazon 联盟 PartnerTag", "official_global", False, "联盟推广位 Tag（通常以 -20 结尾）"),
    "AMAZON_PARTNER_TYPE": ("Amazon PartnerType", "official_global", False, "默认 Associates；其他联盟类型可改"),
    "AMAZON_REGION": ("Amazon 站点 Region", "official_global", False, "us-east-1=美亚 / eu-west-1=英亚 / us-west-2=日亚"),
    "AMAZON_HOST": ("Amazon 接口 Host", "official_global", False, "留空自动按 Region 识别；也可手动填 webservices.amazon.com"),
    "SHOPEE_PARTNER_ID": ("Shopee PartnerID", "official_global", False, "Shopee 开放平台应用 Partner ID"),
    "SHOPEE_PARTNER_KEY": ("Shopee PartnerKey", "official_global", True, "Shopee 开放平台应用 Partner Key"),
    "SHOPEE_ACCESS_TOKEN": ("Shopee AccessToken", "official_global", True, "商家授权 access_token（必填）"),
    "SHOPEE_SHOP_ID": ("Shopee ShopID", "official_global", False, "要监控的店铺 shop_id"),
    "ALIEXPRESS_OPEN_APP_KEY": ("AliExpress AppKey", "official_global", False, "open.aliexpress.com 联盟应用 AppKey"),
    "ALIEXPRESS_OPEN_APP_SECRET": ("AliExpress AppSecret", "official_global", True, "联盟应用 AppSecret"),
    "ALIEXPRESS_OPEN_ACCESS_TOKEN": ("AliExpress AccessToken", "official_global", True, "联盟推广者授权 access_token（必填）"),
    "ALIEXPRESS_SORT": ("AliExpress 排序", "official_global", False, "默认 total_sales_des（销量降序）"),
    "ALIEXPRESS_CURRENCY": ("AliExpress 币种", "official_global", False, "默认 USD"),
    "ALIEXPRESS_TRACKING_ID": ("AliExpress 追踪ID", "official_global", False, "可选；联盟推广 tracking_id"),    # 推送
    "SHOPMONITOR_WEBHOOK_URL": ("告警 Webhook", "push", False, "企业微信/钉钉/飞书群机器人地址，留空=只本机记录"),
    "ALERT_EMAIL_SMTP_HOST": ("邮件 SMTP 服务器", "push", False, "如 smtp.qq.com / smtp.163.com"),
    "ALERT_EMAIL_SMTP_PORT": ("邮件 SMTP 端口", "push", False, "SSL 465 / STARTTLS 587"),
    "ALERT_EMAIL_USER": ("邮件账号", "push", False, "发件邮箱（SMTP 登录账号）"),
    "ALERT_EMAIL_PASS": ("邮件授权码", "push", True, "SMTP 授权码（非登录密码）"),
    "ALERT_EMAIL_FROM": ("邮件发件人", "push", False, "留空用邮件账号"),
    "ALERT_EMAIL_TO": ("邮件收件人", "push", False, "多个用逗号分隔"),
    "ALERT_TELEGRAM_BOT_TOKEN": ("Telegram Bot Token", "push", True, "BotFather 创建机器人获取"),
    "ALERT_TELEGRAM_CHAT_ID": ("Telegram Chat ID", "push", False, "接收告警的会话 ID"),
    # 套餐
    "SHOPMONITOR_PLAN": ("套餐", "plan", False, "free / pro / enterprise"),
}


def ui_config_value(key: str) -> str:
    """返回当前配置值（敏感项做掩码，只显示后 4 位）。"""
    v = os.environ.get(key, "")
    if not v:
        return ""
    schema = UI_CONFIG_SCHEMA.get(key)
    if schema and schema[2]:  # 敏感
        return v[:4] + "****" + v[-4:] if len(v) > 8 else "****"
    return v


def rewrite_env_file(updates: dict) -> None:
    """把更新写回 配置文件.env（保持原有注释/结构），并同步到 os.environ。"""
    p = BASE_DIR / "配置文件.env"
    if p.exists():
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
    else:
        lines = []
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                v = updates.pop(k)
                out.append(f"{k}={v}\n" if v else f"{k}=\n")
                continue
        out.append(line)
    for k, v in updates.items():
        out.append(f"{k}={v}\n" if v else f"{k}=\n")
    p.write_text("".join(out), encoding="utf-8")
    for k, v in updates.items():
        os.environ[k] = v

