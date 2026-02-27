"""Lexa AI — Kommunikation
E-Mail (SMTP/IMAP), Telegram Bot, Discord Bot
"""

import smtplib
import imaplib
import email
import email.mime.text
import email.mime.multipart
import logging
import keyring
from datetime import datetime

logger = logging.getLogger("lexa.comm")


# ══════════════════════════════════════════════
#  E-MAIL (Gmail SMTP/IMAP — App Password)
# ══════════════════════════════════════════════

def _get_email_creds() -> tuple[str, str]:
    """Get email credentials from keyring."""
    addr = keyring.get_password("lexa-ai", "email_address")
    pwd = keyring.get_password("lexa-ai", "email_app_password")
    if not addr or not pwd:
        raise ValueError(
            "E-Mail nicht konfiguriert. Bitte 'email_address' und 'email_app_password' "
            "im Keyring speichern (Gmail → App-Passwort erstellen)."
        )
    return addr, pwd


def email_send(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail SMTP."""
    addr, pwd = _get_email_creds()

    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(email.mime.text.MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(addr, pwd)
            server.send_message(msg)
        logger.info(f"Email sent to {to}")
        return f"E-Mail an {to} gesendet: '{subject}'"
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return f"E-Mail Fehler: {e}"


def email_read(count: int = 5, folder: str = "INBOX") -> list[dict]:
    """Read recent emails via IMAP."""
    addr, pwd = _get_email_creds()

    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", timeout=15) as mail:
            mail.login(addr, pwd)
            mail.select(folder, readonly=True)

            _, data = mail.search(None, "ALL")
            ids = data[0].split()
            recent_ids = ids[-count:] if len(ids) >= count else ids

            emails = []
            for eid in reversed(recent_ids):
                _, msg_data = mail.fetch(eid, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="ignore")[:500]
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")[:500]

                emails.append({
                    "from": msg.get("From", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "preview": body[:200],
                })

            return emails
    except Exception as e:
        logger.error(f"Email read failed: {e}")
        return [{"error": str(e)}]


# ══════════════════════════════════════════════
#  TELEGRAM BOT
# ══════════════════════════════════════════════

def _get_telegram_creds() -> tuple[str, str]:
    """Get Telegram bot token and chat ID from keyring."""
    token = keyring.get_password("lexa-ai", "telegram_bot_token")
    chat_id = keyring.get_password("lexa-ai", "telegram_chat_id")
    if not token or not chat_id:
        raise ValueError(
            "Telegram nicht konfiguriert. Bitte 'telegram_bot_token' und "
            "'telegram_chat_id' im Keyring speichern."
        )
    return token, chat_id


def telegram_send(message: str) -> str:
    """Send a message via Telegram bot."""
    import requests
    token, chat_id = _get_telegram_creds()

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }, timeout=10)

    if resp.status_code == 200:
        return "Telegram-Nachricht gesendet."
    return f"Telegram Fehler: {resp.text}"


def telegram_read(count: int = 5) -> list[dict]:
    """Read recent Telegram messages."""
    import requests
    token, _ = _get_telegram_creds()

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    resp = requests.get(url, params={"limit": count, "offset": -count}, timeout=10)

    if resp.status_code != 200:
        return [{"error": resp.text}]

    updates = resp.json().get("result", [])
    messages = []
    for u in updates:
        msg = u.get("message", {})
        if msg:
            messages.append({
                "from": msg.get("from", {}).get("first_name", "Unknown"),
                "text": msg.get("text", ""),
                "date": datetime.fromtimestamp(msg.get("date", 0)).isoformat(),
            })
    return messages


# ══════════════════════════════════════════════
#  DISCORD BOT (Webhook-basiert, kein Bot nötig)
# ══════════════════════════════════════════════

def _get_discord_webhook() -> str:
    """Get Discord webhook URL from keyring."""
    url = keyring.get_password("lexa-ai", "discord_webhook_url")
    if not url:
        raise ValueError(
            "Discord nicht konfiguriert. Bitte 'discord_webhook_url' im Keyring speichern."
        )
    return url


def discord_send(message: str, username: str = "Lexa AI") -> str:
    """Send a message via Discord webhook."""
    import requests
    webhook_url = _get_discord_webhook()

    resp = requests.post(webhook_url, json={
        "content": message,
        "username": username,
    }, timeout=10)

    if resp.status_code in (200, 204):
        return "Discord-Nachricht gesendet."
    return f"Discord Fehler: {resp.text}"
