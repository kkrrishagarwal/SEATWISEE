"""Notification service: honest statuses, dedupe, templates, provider failure handling (no network)."""
import pytest

from database import db_manager as db
from services import email_service, notification_service as ns, whatsapp_service


@pytest.fixture
def conn():
    c = db.get_conn(":memory:")
    db.seed_demo(c, n_applicants=10)
    return c


def test_unconfigured_providers_are_reported_not_faked(conn, monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"):
        monkeypatch.delenv(k, raising=False)
    assert not email_service.is_configured() and not whatsapp_service.is_configured()
    res = ns.notify(conn, 1, "application_submitted", {"n_prefs": "3"})
    assert res == {"in_app": "sent", "email": "not_configured", "whatsapp": "not_configured"}
    st = ns.integration_status()
    assert "missing" in st["email"]["text"] and "missing" in st["whatsapp"]["text"]


def test_dedupe_prevents_double_send(conn):
    ns.notify(conn, 2, "provisional_offer", {"program": "CSE"}, dedupe="offer:1")
    again = ns.notify(conn, 2, "provisional_offer", {"program": "CSE"}, dedupe="offer:1")
    assert set(again.values()) == {"duplicate"}
    assert len(db.load_notifications(conn, 2)) == 3


def test_email_failure_is_recorded(conn, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1"); monkeypatch.setenv("SMTP_PORT", "1"); monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    assert email_service.is_configured()
    status, detail = email_service.send_email("x@y.z", "s", "<p>b</p>", timeout=2)
    assert status == "failed" and detail
    res = ns.notify(conn, 3, "waitlisted", channels=("email",))
    assert res["email"] == "failed"
    row = db.load_notifications(conn, 3).iloc[0]
    assert row.status == "failed" and row.provider_response


def test_whatsapp_bad_phone_and_unreachable(conn, monkeypatch):
    assert whatsapp_service.normalise_phone("98765 43210") == "919876543210"
    assert whatsapp_service.normalise_phone("12") is None
    monkeypatch.setenv("WHATSAPP_TOKEN", "t"); monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(whatsapp_service.requests, "post", lambda *a, **k: (_ for _ in ()).throw(whatsapp_service.requests.ConnectionError("offline")))
    status, detail = whatsapp_service.send_whatsapp("9876543210", "hi")
    assert status == "failed" and "ConnectionError" in detail
    assert whatsapp_service.send_whatsapp("12", "hi")[0] == "failed"


def test_whatsapp_success_requires_message_id(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "t"); monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    class R:
        ok = True; status_code = 200
        def json(self): return {"messages": [{"id": "wamid.X"}]}
    monkeypatch.setattr(whatsapp_service.requests, "post", lambda *a, **k: R())
    assert whatsapp_service.send_whatsapp("9876543210", "hi") == ("sent", "message id wamid.X")
    class Bad(R):
        ok = False; status_code = 400
        def json(self): return {"error": {"message": "bad token"}}
    monkeypatch.setattr(whatsapp_service.requests, "post", lambda *a, **k: Bad())
    assert whatsapp_service.send_whatsapp("9876543210", "hi")[0] == "failed"


def test_admin_test_send_records_rows(conn):
    out = ns.send_test(conn, "someone@example.com", "9876543210")
    assert set(out) == {"email", "whatsapp"}
    df = db.load_notifications(conn)
    assert (df.event == "test").sum() == 2
