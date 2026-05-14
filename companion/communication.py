"""Lexa AI — Kommunikation
E-Mail (SMTP/IMAP), Telegram Bot, Discord Bot
"""

import smtplib
import imaplib
import email
import email.mime.text
import email.mime.multipart
import email.mime.base
import email.encoders
import logging
import os
import keyring
from datetime import datetime, timedelta
from pathlib import Path
from backend.i18n import t

logger = logging.getLogger("lexa.comm")


# ══════════════════════════════════════════════
#  E-MAIL — Universal SMTP/IMAP (any provider)
#  Supports Gmail, Outlook, Yahoo, GMX, custom servers
# ══════════════════════════════════════════════

# Well-known providers — auto-detected from email domain
_EMAIL_PROVIDERS: dict[str, dict] = {
    "gmail.com": {"smtp": "smtp.gmail.com", "smtp_port": 465, "imap": "imap.gmail.com", "ssl": True},
    "googlemail.com": {"smtp": "smtp.gmail.com", "smtp_port": 465, "imap": "imap.gmail.com", "ssl": True},
    "outlook.com": {"smtp": "smtp-mail.outlook.com", "smtp_port": 587, "imap": "outlook.office365.com", "ssl": False, "starttls": True},
    "hotmail.com": {"smtp": "smtp-mail.outlook.com", "smtp_port": 587, "imap": "outlook.office365.com", "ssl": False, "starttls": True},
    "live.com": {"smtp": "smtp-mail.outlook.com", "smtp_port": 587, "imap": "outlook.office365.com", "ssl": False, "starttls": True},
    "yahoo.com": {"smtp": "smtp.mail.yahoo.com", "smtp_port": 465, "imap": "imap.mail.yahoo.com", "ssl": True},
    "yahoo.de": {"smtp": "smtp.mail.yahoo.com", "smtp_port": 465, "imap": "imap.mail.yahoo.com", "ssl": True},
    "gmx.de": {"smtp": "mail.gmx.net", "smtp_port": 465, "imap": "imap.gmx.net", "ssl": True},
    "gmx.net": {"smtp": "mail.gmx.net", "smtp_port": 465, "imap": "imap.gmx.net", "ssl": True},
    "gmx.at": {"smtp": "mail.gmx.net", "smtp_port": 465, "imap": "imap.gmx.net", "ssl": True},
    "web.de": {"smtp": "smtp.web.de", "smtp_port": 587, "imap": "imap.web.de", "ssl": False, "starttls": True},
    "t-online.de": {"smtp": "securesmtp.t-online.de", "smtp_port": 465, "imap": "secureimap.t-online.de", "ssl": True},
    "icloud.com": {"smtp": "smtp.mail.me.com", "smtp_port": 587, "imap": "imap.mail.me.com", "ssl": False, "starttls": True},
    "me.com": {"smtp": "smtp.mail.me.com", "smtp_port": 587, "imap": "imap.mail.me.com", "ssl": False, "starttls": True},
    "protonmail.com": {"smtp": "smtp.protonmail.ch", "smtp_port": 465, "imap": "imap.protonmail.ch", "ssl": True},
    "proton.me": {"smtp": "smtp.protonmail.ch", "smtp_port": 465, "imap": "imap.protonmail.ch", "ssl": True},
    "zoho.com": {"smtp": "smtp.zoho.com", "smtp_port": 465, "imap": "imap.zoho.com", "ssl": True},
    "aol.com": {"smtp": "smtp.aol.com", "smtp_port": 465, "imap": "imap.aol.com", "ssl": True},
    "mail.de": {"smtp": "smtp.mail.de", "smtp_port": 465, "imap": "imap.mail.de", "ssl": True},
    "posteo.de": {"smtp": "posteo.de", "smtp_port": 465, "imap": "posteo.de", "ssl": True},
    "mailbox.org": {"smtp": "smtp.mailbox.org", "smtp_port": 465, "imap": "imap.mailbox.org", "ssl": True},
}


def _detect_email_provider(email_addr: str) -> dict:
    """Auto-detect SMTP/IMAP settings from email domain.

    Returns provider config dict, or default SSL settings for unknown domains.
    """
    domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""
    if domain in _EMAIL_PROVIDERS:
        return _EMAIL_PROVIDERS[domain]

    # Check for custom server settings in keyring
    try:
        custom_smtp = keyring.get_password("lexa-ai", "email_smtp_server")
        custom_imap = keyring.get_password("lexa-ai", "email_imap_server")
        if custom_smtp:
            custom_port = keyring.get_password("lexa-ai", "email_smtp_port")
            return {
                "smtp": custom_smtp,
                "smtp_port": int(custom_port) if custom_port else 465,
                "imap": custom_imap or f"imap.{domain}",
                "ssl": True,
            }
    except Exception:
        pass

    # Fallback: try common patterns
    return {
        "smtp": f"smtp.{domain}",
        "smtp_port": 465,
        "imap": f"imap.{domain}",
        "ssl": True,
    }


def _get_email_creds() -> tuple[str, str]:
    """Get email credentials from keyring."""
    try:
        addr = keyring.get_password("lexa-ai", "email_address")
        pwd = keyring.get_password("lexa-ai", "email_app_password")
    except Exception as e:
        raise ValueError(t("error.keyringError", error=str(e))) from e
    if not addr or not pwd:
        raise ValueError(
            t("communication.emailKeyringHint")
        )
    return addr, pwd


# Blocked attachment extensions (security)
_BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".scr", ".pif", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".wsh", ".msi", ".msp", ".ps1", ".ps2",
    ".reg", ".inf", ".lnk", ".cpl", ".hta", ".dll", ".sys",
}

# Max attachment size: 25 MB
_MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024


def email_send(to: str, subject: str, body: str, attachment_path: str = "") -> str:
    """Send an email via auto-detected SMTP provider.

    Supports any email provider: Gmail, Outlook, Yahoo, GMX, web.de, iCloud,
    Protonmail, custom SMTP servers, etc. Provider is auto-detected from
    the sender's email domain, or uses custom settings from keyring.

    Optional: attach a file via attachment_path (max 25MB, blocked extensions filtered).
    """
    import re
    addr, pwd = _get_email_creds()
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', to.strip()):
        return t("validation.invalidEmail", email=to)
    subject = subject[:500]
    body = body[:50000]

    provider = _detect_email_provider(addr)

    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(email.mime.text.MIMEText(body, "plain"))

    # Handle attachment if provided
    if attachment_path:
        attachment_path = attachment_path.strip()
        file_path = Path(attachment_path).resolve()

        # Security: prevent path traversal — must be a real file
        if not file_path.exists() or not file_path.is_file():
            return t("error.notFound", path=str(file_path))

        # Check blocked extensions
        ext = file_path.suffix.lower()
        if ext in _BLOCKED_EXTENSIONS:
            return t("email.attachmentBlocked", ext=ext)

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > _MAX_ATTACHMENT_SIZE:
            size_mb = round(file_size / 1024 / 1024, 1)
            return t("email.attachmentTooLarge", size=f"{size_mb}MB", max="25MB")

        # Attach the file
        try:
            with open(file_path, "rb") as f:
                part = email.mime.base.MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            email.encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename=\"{file_path.name}\"",
            )
            msg.attach(part)
        except Exception as e:
            logger.error(f"Attachment read failed: {e}", exc_info=True)
            return t("communication.emailError", error=f"Attachment: {e}")

    try:
        smtp_host = provider["smtp"]
        smtp_port = provider["smtp_port"]

        if provider.get("ssl", True):
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(addr, pwd)
                server.send_message(msg)
        elif provider.get("starttls"):
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(addr, pwd)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.login(addr, pwd)
                server.send_message(msg)

        logger.info(f"Email sent to {to} via {smtp_host}")
        if attachment_path:
            return t("email.attachmentSent", to=to, subject=subject, file=Path(attachment_path).name)
        return f"E-Mail an {to} gesendet: '{subject}'"
    except smtplib.SMTPAuthenticationError:
        domain = addr.split("@")[-1] if "@" in addr else "unbekannt"
        return (f"E-Mail-Authentifizierung fehlgeschlagen ({domain}).\n"
                f"Prüfe: App-Passwort korrekt? 2FA aktiv? Weniger sichere Apps erlaubt?")
    except smtplib.SMTPConnectError as e:
        return f"SMTP-Server nicht erreichbar ({provider['smtp']}:{provider['smtp_port']}): {e}"
    except Exception as e:
        logger.error(f"Email send failed: {e}", exc_info=True)
        return t("communication.emailError", error=str(e))


def _parse_email_message(msg, eid: bytes = b"", flags_str: str = "") -> dict:
    """Parse an email.message.Message into a structured dict.

    Shared helper for email_read, email_search, email_summarize.
    """
    body = ""
    has_attachments = False

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            # Detect attachments
            if "attachment" in disposition.lower():
                has_attachments = True

            if content_type == "text/plain" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors="ignore")[:500]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(errors="ignore")[:500]

    # Determine read status from flags
    is_read = "\\Seen" in flags_str if flags_str else True

    return {
        "message_id": msg.get("Message-ID", ""),
        "from": msg.get("From", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "preview": body[:200],
        "is_read": is_read,
        "has_attachments": has_attachments,
    }


def email_read(count: int = 10, folder: str = "INBOX",
               unread_only: bool = False, sender: str = "") -> list[dict]:
    """Read recent emails via auto-detected IMAP provider.

    Supports any email provider — auto-detected from sender's email domain.

    Args:
        count: Number of emails to return (default 10, max 50).
        folder: IMAP folder to read from (default INBOX).
        unread_only: If True, only return unread (UNSEEN) messages.
        sender: If set, filter by sender email address or name (partial match).
    """
    count = max(1, min(50, count))
    addr, pwd = _get_email_creds()
    provider = _detect_email_provider(addr)
    imap_host = provider.get("imap", "imap.gmail.com")

    try:
        with imaplib.IMAP4_SSL(imap_host, timeout=15) as mail:
            mail.login(addr, pwd)
            mail.select(folder, readonly=True)

            # Build IMAP search criteria
            if unread_only:
                _, data = mail.search(None, "UNSEEN")
            else:
                _, data = mail.search(None, "ALL")

            ids = data[0].split()
            # Take more IDs than requested if filtering by sender
            fetch_count = count * 3 if sender else count
            recent_ids = ids[-fetch_count:] if len(ids) >= fetch_count else ids

            emails = []
            sender_lower = sender.lower().strip() if sender else ""

            for eid in reversed(recent_ids):
                if len(emails) >= count:
                    break

                # Fetch message with FLAGS to determine read status
                _, msg_data = mail.fetch(eid, "(FLAGS RFC822)")

                # Parse flags from response
                flags_str = ""
                raw_msg = None
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        header = response_part[0].decode(errors="ignore") if isinstance(response_part[0], bytes) else str(response_part[0])
                        if "FLAGS" in header:
                            flags_str = header
                        raw_msg = response_part[1]

                if raw_msg is None:
                    continue

                msg = email.message_from_bytes(raw_msg)

                # Filter by sender if specified
                if sender_lower:
                    msg_from = msg.get("From", "").lower()
                    if sender_lower not in msg_from:
                        continue

                emails.append(_parse_email_message(msg, eid, flags_str))

            return emails
    except imaplib.IMAP4.error as e:
        err_str = str(e).lower()
        if "authentication" in err_str or "login" in err_str:
            domain = addr.split("@")[-1] if "@" in addr else "unbekannt"
            return [{"error": f"IMAP-Login fehlgeschlagen ({domain}). App-Passwort prüfen."}]
        return [{"error": str(e)}]
    except Exception as e:
        logger.error(f"Email read failed: {e}", exc_info=True)
        return [{"error": str(e)}]


def email_search(query: str, sender: str = "", days: int = 7) -> list[dict]:
    """Search emails by keyword in subject/body within a time range.

    Uses IMAP SEARCH with SUBJECT/BODY/FROM criteria.

    Args:
        query: Search keyword (required). Searched in subject and body.
        sender: Optional sender filter (email address or name).
        days: Search within the last N days (default 7, max 365).
    """
    if not query or not query.strip():
        return [{"error": "Kein Suchbegriff angegeben."}]

    query = query.strip()[:200]
    days = max(1, min(365, days))

    addr, pwd = _get_email_creds()
    provider = _detect_email_provider(addr)
    imap_host = provider.get("imap", "imap.gmail.com")

    try:
        with imaplib.IMAP4_SSL(imap_host, timeout=15) as mail:
            mail.login(addr, pwd)
            mail.select("INBOX", readonly=True)

            # Build date criterion
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

            # Search in subject first, then body — IMAP OR syntax
            # IMAP SEARCH: OR (SUBJECT "query") (BODY "query") SINCE date
            search_query = query.replace('"', '\\"')

            criteria_parts = [f'SINCE {since_date}']
            if sender:
                safe_sender = sender.strip()[:200].replace('"', '\\"')
                criteria_parts.append(f'FROM "{safe_sender}"')

            # Search subject OR body with the query
            subject_criteria = " ".join(criteria_parts + [f'SUBJECT "{search_query}"'])
            body_criteria = " ".join(criteria_parts + [f'BODY "{search_query}"'])

            # Get IDs from both searches and merge (dedup)
            _, subj_data = mail.search(None, subject_criteria)
            _, body_data = mail.search(None, body_criteria)

            subj_ids = set(subj_data[0].split()) if subj_data[0] else set()
            body_ids = set(body_data[0].split()) if body_data[0] else set()
            all_ids = sorted(subj_ids | body_ids, key=lambda x: int(x))

            if not all_ids:
                return [{"info": t("email.noResults", query=query)}]

            # Limit to last 20 results
            result_ids = all_ids[-20:]

            emails = []
            for eid in reversed(result_ids):
                _, msg_data = mail.fetch(eid, "(FLAGS RFC822)")

                flags_str = ""
                raw_msg = None
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        header = response_part[0].decode(errors="ignore") if isinstance(response_part[0], bytes) else str(response_part[0])
                        if "FLAGS" in header:
                            flags_str = header
                        raw_msg = response_part[1]

                if raw_msg is None:
                    continue

                msg = email.message_from_bytes(raw_msg)
                emails.append(_parse_email_message(msg, eid, flags_str))

            return emails
    except imaplib.IMAP4.error as e:
        err_str = str(e).lower()
        if "authentication" in err_str or "login" in err_str:
            domain = addr.split("@")[-1] if "@" in addr else "unbekannt"
            return [{"error": f"IMAP-Login fehlgeschlagen ({domain}). App-Passwort prüfen."}]
        return [{"error": str(e)}]
    except Exception as e:
        logger.error(f"Email search failed: {e}", exc_info=True)
        return [{"error": str(e)}]


def email_summarize(count: int = 5) -> list[dict]:
    """Read last N unread emails and return structured data for LLM summarization.

    Returns rich structured data (sender, subject, preview, date) that the LLM
    can use to generate a natural-language summary in conversation context.

    Args:
        count: Number of unread emails to summarize (default 5, max 20).
    """
    count = max(1, min(20, count))

    # Reuse email_read with unread_only=True
    emails = email_read(count=count, unread_only=True)

    # Check for errors
    if emails and "error" in emails[0]:
        return emails

    if not emails:
        return [{"info": t("email.noResults", query="unread")}]

    # Build structured summary data for LLM context
    summary = {
        "total_unread": len(emails),
        "summarized": t("email.summarized", count=len(emails)),
        "emails": [],
    }

    for i, em in enumerate(emails, 1):
        summary["emails"].append({
            "index": i,
            "from": em.get("from", ""),
            "subject": em.get("subject", ""),
            "date": em.get("date", ""),
            "preview": em.get("preview", ""),
            "has_attachments": em.get("has_attachments", False),
        })

    return [summary]


# ══════════════════════════════════════════════
#  TELEGRAM BOT
# ══════════════════════════════════════════════

def _get_telegram_creds() -> tuple[str, str]:
    """Get Telegram bot token and chat ID from keyring."""
    try:
        token = keyring.get_password("lexa-ai", "telegram_bot_token")
        chat_id = keyring.get_password("lexa-ai", "telegram_chat_id")
    except Exception as e:
        raise ValueError(t("error.keyringError", error=str(e))) from e
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
    message = message[:4096]  # Telegram max message length

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }, timeout=10)

    if resp.status_code == 200:
        return t("communication.telegramSent")
    return t("communication.telegramError", error=resp.text)


def _get_telegram_offset_path() -> Path:
    """Path to store the last Telegram update_id for proper offset tracking."""
    import os as _os
    data_dir = _os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent))
    return Path(data_dir) / ".telegram_offset"


def _load_telegram_offset() -> int | None:
    """Load the last processed Telegram update_id."""
    path = _get_telegram_offset_path()
    try:
        if path.exists():
            val = path.read_text().strip()
            return int(val) if val else None
    except (ValueError, OSError):
        pass
    return None


def _save_telegram_offset(offset: int) -> None:
    """Save the last processed Telegram update_id."""
    try:
        _get_telegram_offset_path().write_text(str(offset))
    except OSError:
        pass


def telegram_read(count: int = 5) -> list[dict]:
    """Read recent Telegram messages with proper offset tracking.

    Uses Telegram's offset parameter correctly:
    - Tracks last processed update_id in a file
    - Each call returns only NEW messages since last read
    - No duplicate messages across calls
    - First call (no offset) returns last `count` messages
    """
    import requests
    token, _ = _get_telegram_creds()
    count = max(1, min(100, count))

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"limit": count, "timeout": 5}

    # Use stored offset to get only new messages
    last_offset = _load_telegram_offset()
    if last_offset is not None:
        params["offset"] = last_offset + 1

    resp = requests.get(url, params=params, timeout=15)

    if resp.status_code != 200:
        return [{"error": resp.text}]

    data = resp.json()
    if not data.get("ok"):
        return [{"error": data.get("description", "Telegram API Fehler")}]

    updates = data.get("result", [])
    messages = []
    max_update_id = last_offset

    for u in updates:
        update_id = u.get("update_id", 0)
        if max_update_id is None or update_id > max_update_id:
            max_update_id = update_id

        msg = u.get("message", {})
        if msg:
            messages.append({
                "from": msg.get("from", {}).get("first_name", "Unknown"),
                "text": msg.get("text", ""),
                "date": datetime.fromtimestamp(msg.get("date", 0)).isoformat(),
                "chat_id": msg.get("chat", {}).get("id"),
            })

    # Save offset so next call doesn't return these messages again
    if max_update_id is not None and max_update_id != last_offset:
        _save_telegram_offset(max_update_id)

    return messages


# ══════════════════════════════════════════════
#  DISCORD BOT (Webhook-basiert, kein Bot nötig)
# ══════════════════════════════════════════════

def _get_discord_webhook() -> str:
    """Get Discord webhook URL from keyring."""
    try:
        url = keyring.get_password("lexa-ai", "discord_webhook_url")
    except Exception as e:
        raise ValueError(t("error.keyringError", error=str(e))) from e
    if not url:
        raise ValueError(
            "Discord nicht konfiguriert. Bitte 'discord_webhook_url' im Keyring speichern."
        )
    if "discord.com/api/webhooks" not in url and "discordapp.com/api/webhooks" not in url:
        raise ValueError(t("validation.invalidDiscordWebhook"))
    return url


def discord_send(message: str, username: str = "Lexa AI") -> str:
    """Send a message via Discord webhook."""
    import requests
    webhook_url = _get_discord_webhook()
    message = message[:2000]   # Discord max message length
    username = username[:80]   # Discord max username length

    resp = requests.post(webhook_url, json={
        "content": message,
        "username": username,
    }, timeout=10)

    if resp.status_code in (200, 204):
        return t("communication.discordSent")
    return t("communication.discordError", error=resp.text)
