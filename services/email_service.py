"""SMTP email delivery. Reads configuration from environment variables or Streamlit secrets.

Never claims success unless the SMTP server accepted the message. Returns (status, detail):
  status in {"sent", "failed", "not_configured"}.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional, Tuple

REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    if val:
        return val
    try:  # Streamlit secrets, when running under Streamlit with a secrets.toml
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def config() -> dict:
    return {
        "host": _get("SMTP_HOST"),
        "port": int(_get("SMTP_PORT", "587") or 587),
        "user": _get("SMTP_USER"),
        "password": _get("SMTP_PASSWORD"),
        "sender": _get("SMTP_FROM") or _get("SMTP_USER"),
        "tls": (_get("SMTP_TLS", "starttls") or "starttls").lower(),   # starttls | ssl | none
    }


def is_configured() -> bool:
    return all(_get(k) for k in REQUIRED)


def status_text() -> str:
    if is_configured():
        c = config()
        return f"configured · {c['host']}:{c['port']} as {c['user']} ({c['tls']})"
    missing = [k for k in REQUIRED if not _get(k)]
    return "not configured · missing " + ", ".join(missing)


# Credentials the server rejected, keyed by (host, user, password hash). While the same credentials are configured,
# further sends fail immediately instead of opening a new connection and waiting for another 535.
_REJECTED: dict = {}


def _cred_key() -> tuple:
    import hashlib
    c = config()
    return (c["host"], c["user"], hashlib.sha256((c["password"] or "").encode()).hexdigest())


def send_email(to: str, subject: str, html_body: str, text_body: Optional[str] = None, timeout: int = 20) -> Tuple[str, str]:
    if not is_configured():
        return "not_configured", "SMTP credentials missing: " + ", ".join(k for k in REQUIRED if not _get(k))
    if _cred_key() in _REJECTED:
        return "failed", _REJECTED[_cred_key()] + " (not retried until the credentials change)"
    if not to or "@" not in to:
        return "failed", "invalid recipient"
    c = config()
    msg = EmailMessage()
    msg["From"] = c["sender"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body or _strip_html(html_body))
    msg.add_alternative(html_body, subtype="html")
    try:
        if c["tls"] == "ssl":
            with smtplib.SMTP_SSL(c["host"], c["port"], timeout=timeout, context=ssl.create_default_context(), local_hostname="seatwisee.local") as s:
                _login(s, c["user"], c["password"])
                refused = s.send_message(msg)
        else:
            with smtplib.SMTP(c["host"], c["port"], timeout=timeout, local_hostname="seatwisee.local") as s:
                s.ehlo()
                if c["tls"] == "starttls":
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                _login(s, c["user"], c["password"])
                refused = s.send_message(msg)
        if refused:
            return "failed", f"recipients refused: {refused}"
        return "sent", "accepted by SMTP server"
    except smtplib.SMTPAuthenticationError as e:
        _REJECTED[_cred_key()] = f"authentication failed: {e.smtp_code} {e.smtp_error!r}"
        return "failed", _REJECTED[_cred_key()]
    except (smtplib.SMTPException, OSError) as e:
        return "failed", f"{type(e).__name__}: {e}"


def forget_rejection() -> None:
    """Allow a fresh attempt with the current credentials (used by the admin 'Send Test' button)."""
    _REJECTED.pop(_cred_key(), None)


class SMTPSession:
    """One SMTP connection for many messages. After an authentication or connection failure it stops
    contacting the server and returns the same failure for every remaining message (no repeated timeouts)."""

    def __init__(self, timeout: int = 20):
        self.timeout, self.server, self.dead = timeout, None, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            if self.server is not None:
                self.server.quit()
        except Exception:
            pass

    def _connect(self):
        c = config()
        if c["tls"] == "ssl":
            s = smtplib.SMTP_SSL(c["host"], c["port"], timeout=self.timeout, context=ssl.create_default_context(), local_hostname="seatwisee.local")
        else:
            s = smtplib.SMTP(c["host"], c["port"], timeout=self.timeout, local_hostname="seatwisee.local"); s.ehlo()
            if c["tls"] == "starttls":
                s.starttls(context=ssl.create_default_context()); s.ehlo()
        _login(s, c["user"], c["password"])
        self.server = s

    def send(self, to: str, subject: str, html_body: str, text_body: Optional[str] = None) -> Tuple[str, str]:
        if not is_configured():
            return "not_configured", "SMTP credentials missing: " + ", ".join(k for k in REQUIRED if not _get(k))
        if self.dead:
            return "failed", self.dead
        if _cred_key() in _REJECTED:
            self.dead = _REJECTED[_cred_key()] + " (not retried until the credentials change)"; return "failed", self.dead
        if not to or "@" not in to:
            return "failed", "invalid recipient"
        msg = EmailMessage(); msg["From"] = config()["sender"]; msg["To"] = to; msg["Subject"] = subject
        msg.set_content(text_body or _strip_html(html_body)); msg.add_alternative(html_body, subtype="html")
        for attempt in (1, 2):   # one reconnect if the server dropped an idle connection
            try:
                if self.server is None:
                    self._connect()
                refused = self.server.send_message(msg)
                return ("failed", f"recipients refused: {refused}") if refused else ("sent", "accepted by SMTP server")
            except smtplib.SMTPAuthenticationError as e:
                self.dead = _REJECTED[_cred_key()] = f"authentication failed: {e.smtp_code} {e.smtp_error!r}"; return "failed", self.dead
            except smtplib.SMTPServerDisconnected as e:
                self.server = None
                if attempt == 2:
                    self.dead = f"SMTPServerDisconnected: {e}"; return "failed", self.dead
            except (smtplib.SMTPException, OSError) as e:
                if self.server is None:   # could not connect at all: stop trying for the rest of the batch
                    self.dead = f"{type(e).__name__}: {e}"
                return "failed", f"{type(e).__name__}: {e}"
        return "failed", "unknown error"


def _login(s: smtplib.SMTP, user: str, password: str) -> None:
    """AUTH PLAIN first (one round-trip, clean 535 on bad credentials); fall back to smtplib's negotiation."""
    if "auth" in s.esmtp_features and "PLAIN" in s.esmtp_features["auth"].upper():
        s.user, s.password = user, password
        s.auth("PLAIN", s.auth_plain)          # raises SMTPAuthenticationError with the server's 535 text
        return
    s.login(user, password)


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
