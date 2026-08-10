# -*- coding: utf-8 -*-
"""通知（Webhook/邮件/Telegram）+ PDF 导出 测试。"""
import os
import tempfile


def test_notify_no_config_returns_false(monkeypatch):
    import shopmonitor.notify as n
    for k in ("ALERT_WEBHOOK_URL", "ALERT_EMAIL_SMTP_HOST", "ALERT_EMAIL_USER",
              "ALERT_EMAIL_PASS", "ALERT_EMAIL_TO", "ALERT_TELEGRAM_BOT_TOKEN",
              "ALERT_TELEGRAM_CHAT_ID"):
        monkeypatch.setattr(n, k, "")
    r = n.send_notify("标题", "内容")
    assert r == {"webhook": False, "email": False, "telegram": False}


def test_to_pdf_compare():
    from shopmonitor.models import CompareRow
    from shopmonitor.report import export_profit_table, md_to_pdf, to_pdf
    rows = [CompareRow(platform="mock", product_id="1", title="测试商品", price=99.0, sales=100)]
    tmp = os.path.join(tempfile.gettempdir(), "t.pdf")
    to_pdf(rows, tmp)
    assert open(tmp, "rb").read()[:4] == b"%PDF"
    os.unlink(tmp)
    items = [{"rank": 1, "product_id": "1", "title": "测试", "price": 99.0,
              "estimated_profit": 10.0, "estimated_margin": 10.1}]
    tmp2 = os.path.join(tempfile.gettempdir(), "t2.pdf")
    export_profit_table(items, "pdf", path=tmp2)
    assert open(tmp2, "rb").read()[:4] == b"%PDF"
    os.unlink(tmp2)
    tmp3 = os.path.join(tempfile.gettempdir(), "t3.pdf")
    md_to_pdf("# 标题\n\n- 列表\n\n| a | b |", tmp3, title="测试")
    assert open(tmp3, "rb").read()[:4] == b"%PDF"
    os.unlink(tmp3)


def test_test_notify_endpoint():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    body = {k: "" for k in ("webhook_url", "email_host", "email_user", "email_pass",
                            "email_to", "telegram_token", "telegram_chat_id")}
    r = c.post("/api/v1/配置/测试通知", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is False
    assert j["channels"] == {"webhook": False, "email": False, "telegram": False}
    assert "details" in j
    assert j["details"]["telegram"]["ok"] is False
    assert "未配置" in j["details"]["telegram"]["error"]


def test_pdf_endpoints():
    from fastapi.testclient import TestClient
    from shopmonitor.api.main import app
    c = TestClient(app)
    j = c.get("/api/v1/rank/mock?category=数码&limit=2&fresh=true").json()
    ids = ",".join(i["product_id"] for i in j["items"])
    r = c.get("/api/v1/report/compare", params={"platform": "mock", "product_ids": ids, "fmt": "pdf"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    r2 = c.get("/api/v1/tools/filter", params={"platform": "mock", "category": "数码", "fmt": "pdf", "limit": 5})
    assert r2.status_code == 200 and r2.content[:4] == b"%PDF"


def test_notify_channel_validation_empty():
    import shopmonitor.notify as nt
    assert nt.test_webhook("")["ok"] is False
    assert nt.test_telegram("", "")["ok"] is False
    assert "未配置" in nt.test_telegram("", "")["error"]
    assert nt.test_email("", 465, "", "", "", "")["ok"] is False


def test_email_validation_ok(monkeypatch):
    import shopmonitor.notify as nt

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def login(self, u, p):
            pass

        def sendmail(self, *a):
            pass

        def quit(self):
            pass

    monkeypatch.setattr(nt.smtplib, "SMTP_SSL", FakeSMTP)
    r = nt.test_email("smtp.qq.com", 465, "user", "pwd", "from", "to@x.com")
    assert r["ok"] is True


def test_telegram_validation_ok(monkeypatch):
    import shopmonitor.notify as nt

    class Resp:
        def __init__(self, payload):
            self.payload = payload
            self.status = 200

        def read(self):
            return self.payload.encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = []

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append(url)
        if "getMe" in url:
            return Resp('{"ok":true,"result":{"username":"bot"}}')
        return Resp('{"ok":true,"result":{"message_id":1}}')

    monkeypatch.setattr(nt.urllib.request, "urlopen", fake_urlopen)
    r = nt.test_telegram("123:tok", "chat123")
    assert r["ok"] is True
    assert len(calls) == 2
