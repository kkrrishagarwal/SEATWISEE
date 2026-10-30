"""WhatsApp Business Cloud API delivery (Meta Graph API).

Configuration (env or Streamlit secrets):
  WHATSAPP_TOKEN            permanent/system-user access token
  WHATSAPP_PHONE_NUMBER_ID  the sender phone number id from the WhatsApp Business account
  WHATSAPP_TEMPLATE         optional approved template name; when set, messages are sent as that
                            template with the text as its single body parameter
  WHATSAPP_API_VERSION      default v20.0
Returns (status, detail). "sent" only when the API returns a message id.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional, Tuple

import requests

REQUIRED = ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID")


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def is_configured() -> bool:
    return all(_get(k) for k in REQUIRED)


def status_text() -> str:
    if is_configured():
        return f"configured · phone number id {_get('WHATSAPP_PHONE_NUMBER_ID')}" + (f" · template {_get('WHATSAPP_TEMPLATE')}" if _get("WHATSAPP_TEMPLATE") else " · free-form text")
    return "not configured · missing " + ", ".join(k for k in REQUIRED if not _get(k))


def normalise_phone(phone: str, default_country: str = "91") -> Optional[str]:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if len(digits) == 10:
        digits = default_country + digits
    return digits if 11 <= len(digits) <= 15 else None


def send_whatsapp(phone: str, text: str, timeout: int = 20) -> Tuple[str, str]:
    if not is_configured():
        return "not_configured", "WhatsApp credentials missing: " + ", ".join(k for k in REQUIRED if not _get(k))
    to = normalise_phone(phone)
    if not to:
        return "failed", "invalid phone number"
    version = _get("WHATSAPP_API_VERSION", "v20.0")
    url = f"https://graph.facebook.com/{version}/{_get('WHATSAPP_PHONE_NUMBER_ID')}/messages"
    headers = {"Authorization": f"Bearer {_get('WHATSAPP_TOKEN')}", "Content-Type": "application/json"}
    template = _get("WHATSAPP_TEMPLATE")
    if template:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "template",
                   "template": {"name": template, "language": {"code": _get("WHATSAPP_TEMPLATE_LANG", "en_US")},
                                "components": [{"type": "body", "parameters": [{"type": "text", "text": text[:1024]}]}]}}
    else:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"preview_url": False, "body": text[:4096]}}
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
    except requests.RequestException as e:
        return "failed", f"{type(e).__name__}: {e}"
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:300]}
    if r.ok and body.get("messages"):
        return "sent", f"message id {body['messages'][0].get('id')}"
    err = body.get("error", {})
    return "failed", f"HTTP {r.status_code}: {err.get('message') or body}"[:500]
