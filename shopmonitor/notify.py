"""统一告警通知：Webhook（企业微信/钉钉/飞书）+ 邮件 + Telegram。

任一通道配置后即启用；未配置自动跳过。所有通道失败都不影响主流程。
"""
import json
import smtplib
import urllib.error
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from typing import Dict

from .config import (
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_PASS,
    ALERT_EMAIL_SMTP_HOST,
    ALERT_EMAIL_SMTP_PORT,
    ALERT_EMAIL_TO,
    ALERT_EMAIL_USER,
    ALERT_TELEGRAM_BOT_TOKEN,
    ALERT_TELEGRAM_CHAT_ID,
    ALERT_WEBHOOK_URL,
)


def _webhook(title: str, message: str, markdown: bool) -> bool:
    if not ALERT_WEBHOOK_URL:
        return False
    if markdown:
        payload = {"msgtype": "markdown", "markdown": {"content": f"{title}\n{message}"}}
    else:
        payload = {"msgtype": "text", "text": {"content": f"{title}\n{message}"}}
    try:
        req = urllib.request.Request(
            ALERT_WEBHOOK_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:  # noqa: BLE001
        return False


def _email(title: str, message: str) -> bool:
    if not (ALERT_EMAIL_SMTP_HOST and ALERT_EMAIL_USER and ALERT_EMAIL_PASS and ALERT_EMAIL_TO):
        return False
    try:
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = Header(title, "utf-8")
        msg["From"] = ALERT_EMAIL_FROM or ALERT_EMAIL_USER
        msg["To"] = ALERT_EMAIL_TO
        if ALERT_EMAIL_SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(ALERT_EMAIL_SMTP_HOST, ALERT_EMAIL_SMTP_PORT, timeout=8)
        else:
            server = smtplib.SMTP(ALERT_EMAIL_SMTP_HOST, ALERT_EMAIL_SMTP_PORT, timeout=8)
            server.starttls()
        server.login(ALERT_EMAIL_USER, ALERT_EMAIL_PASS)
        server.sendmail(ALERT_EMAIL_FROM or ALERT_EMAIL_USER,
                        [x.strip() for x in ALERT_EMAIL_TO.split(",") if x.strip()],
                        msg.as_string())
        server.quit()
        return True
    except Exception:  # noqa: BLE001
        return False


def _telegram(title: str, message: str, markdown: bool) -> bool:
    if not (ALERT_TELEGRAM_BOT_TOKEN and ALERT_TELEGRAM_CHAT_ID):
        return False
    try:
        text = f"{title}\n{message}"
        url = f"https://api.telegram.org/bot{ALERT_TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": ALERT_TELEGRAM_CHAT_ID, "text": text[:4000]}
        if markdown:
            data["parse_mode"] = "Markdown"
        req = urllib.request.Request(
            url, data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=8)
        return True
    except Exception:  # noqa: BLE001
        return False


def send_notify(title: str, message: str, markdown: bool = False) -> Dict[str, bool]:
    """多通道推送，返回各通道是否成功。"""
    return {
        "webhook": _webhook(title, message, markdown),
        "email": _email(title, message),
        "telegram": _telegram(title, message, markdown),
    }

# ---------------- 凭据校验（配置中心「测试通知」用，返回明确错误） ----------------
def test_webhook(url: str = "") -> dict:
    """校验并发送 Webhook 测试消息。"""
    url = url or ALERT_WEBHOOK_URL
    if not url:
        return {"ok": False, "error": "未配置 Webhook 地址"}
    try:
        payload = {"msgtype": "text", "text": {"content": "ShopMonitor 测试通知：Webhook 配置成功 ✅"}}
        req = urllib.request.Request(
            url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            return {"ok": 200 <= r.status < 300, "error": "" if 200 <= r.status < 300 else f"HTTP {r.status}"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}（地址可能无效）"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"网络异常：{e}"}


def test_email(host: str = "", port: int = 465, user: str = "", pwd: str = "",
               from_: str = "", to: str = "") -> dict:
    """校验并发送邮件测试消息（区分：未配置 / 认证失败 / 连接失败）。"""
    host = host or ALERT_EMAIL_SMTP_HOST
    port = int(port or ALERT_EMAIL_SMTP_PORT or 465)
    user = user or ALERT_EMAIL_USER
    pwd = pwd or ALERT_EMAIL_PASS
    to = to or ALERT_EMAIL_TO
    from_ = from_ or ALERT_EMAIL_FROM or user
    if not (host and user and pwd and to):
        return {"ok": False, "error": "未完整配置（服务器/账号/授权码/收件人）"}
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=8)
        else:
            server = smtplib.SMTP(host, port, timeout=8)
            server.starttls()
        try:
            server.login(user, pwd)
        except smtplib.SMTPAuthenticationError:
            server.quit()
            return {"ok": False, "error": "认证失败：账号或授权码错误"}
        msg = MIMEText("ShopMonitor 测试通知：邮件配置成功 ✅", "plain", "utf-8")
        msg["Subject"] = Header("ShopMonitor 测试通知", "utf-8")
        msg["From"] = from_
        msg["To"] = to
        server.sendmail(from_, [x.strip() for x in to.split(",") if x.strip()], msg.as_string())
        server.quit()
        return {"ok": True, "error": ""}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "认证失败：账号或授权码错误"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"发送失败：{e}"}


def test_telegram(token: str = "", chat_id: str = "") -> dict:
    """校验 Telegram：先 getMe 验证 Token，再 sendMessage 验证会话。"""
    token = token or ALERT_TELEGRAM_BOT_TOKEN
    chat_id = chat_id or ALERT_TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return {"ok": False, "error": "未配置 Bot Token 或 Chat ID"}
    try:
        try:
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
            with urllib.request.urlopen(req, timeout=8) as r:
                me = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"ok": False, "error": f"Bot Token 无效（HTTP {e.code}）"}
        if not me.get("ok"):
            return {"ok": False, "error": "Bot Token 无效：" + str(me.get("description", "unknown"))}
        data = {"chat_id": chat_id, "text": "ShopMonitor 测试通知：Telegram 配置成功 ✅"}
        req2 = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req2, timeout=8) as r2:
            res = json.loads(r2.read().decode("utf-8"))
        if res.get("ok"):
            return {"ok": True, "error": ""}
        return {"ok": False, "error": "发送失败：" + str(res.get("description", "unknown"))}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}（服务异常或 Token 无效）"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"网络异常：{e}"}
