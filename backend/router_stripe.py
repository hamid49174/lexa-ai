"""Lexa AI — Stripe Payment Router
API Endpoints für Stripe-Zahlungsintegration (SaaS Website)
"""

import asyncio
import hashlib
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests
import stripe
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.security import check_rate_limit, audit_log
from backend.config import LEXA_DATA_DIR

logger = logging.getLogger("lexa.stripe")
router = APIRouter(tags=["stripe"])

# ── Stripe Configuration ─────────────────────────
_stripe_key = None
_webhook_secret = None
_supabase_service_role_key = None
_supabase_public_key = None
_supabase_url = None

_PRICE_ID_RE = re.compile(r"^price_[A-Za-z0-9_]+$")
_LICENSE_KEY_RE = re.compile(r"^LEXA-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}$")
_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
_KNOWN_SUBSCRIPTION_STATUSES = {
    "active",
    "trialing",
    "past_due",
    "canceled",
    "incomplete",
    "incomplete_expired",
    "unpaid",
    "paused",
}


def _get_keyring_value(secret_name: str) -> str:
    try:
        import keyring

        return keyring.get_password("lexa-ai", secret_name) or ""
    except Exception:
        return ""


def _get_stripe_key() -> str:
    """Get Stripe secret key from environment or keyring."""
    global _stripe_key
    if _stripe_key:
        return _stripe_key
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        key = _get_keyring_value("stripe_secret_key")
    _stripe_key = key
    return key


def _get_webhook_secret() -> str:
    """Get Stripe webhook secret from environment or keyring."""
    global _webhook_secret
    if _webhook_secret:
        return _webhook_secret
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        secret = _get_keyring_value("stripe_webhook_secret")
    _webhook_secret = secret
    return secret


def _init_stripe():
    """Initialize Stripe SDK with API key."""
    key = _get_stripe_key()
    if not key:
        raise ValueError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = key


def _get_supabase_url() -> str:
    global _supabase_url
    if _supabase_url:
        return _supabase_url
    url = os.environ.get("SUPABASE_URL", "") or _get_keyring_value("supabase_url")
    _supabase_url = url.rstrip("/")
    return _supabase_url


def _get_supabase_service_role_key() -> str:
    global _supabase_service_role_key
    if _supabase_service_role_key:
        return _supabase_service_role_key
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or os.environ.get("SUPABASE_SECRET_KEY", "")
        or _get_keyring_value("supabase_service_role_key")
        or _get_keyring_value("supabase_secret_key")
    )
    _supabase_service_role_key = key
    return key


def _get_supabase_public_key() -> str:
    global _supabase_public_key
    if _supabase_public_key:
        return _supabase_public_key
    key = (
        os.environ.get("SUPABASE_ANON_KEY", "")
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
        or _get_keyring_value("supabase_anon_key")
        or _get_keyring_value("supabase_publishable_key")
    )
    _supabase_public_key = key
    return key


def _supabase_configured() -> bool:
    return bool(_get_supabase_url() and _get_supabase_service_role_key())


def _supabase_auth_key() -> str:
    return _get_supabase_public_key() or _get_supabase_service_role_key()


def _supabase_service_headers(prefer: str = "") -> dict[str, str]:
    key = _get_supabase_service_role_key()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return ""
    return authorization[7:].strip()


def _get_allowed_price_ids() -> set[str]:
    raw = (
        os.environ.get("STRIPE_ALLOWED_PRICE_IDS", "")
        or os.environ.get("STRIPE_PRICE_IDS", "")
        or _get_keyring_value("stripe_allowed_price_ids")
    )
    return {item.strip() for item in raw.split(",") if item.strip()}


def _get_price_plan_map() -> dict[str, str]:
    """Deterministische price_id -> plan Zuordnung aus ENV/keyring.

    Format: "price_xxx:ultra,price_yyy:pro". Vorrangige, zuverlaessige Quelle fuer die
    Plan-Klassifizierung — unabhaengig vom optionalen Stripe-nickname.
    """
    raw = (
        os.environ.get("STRIPE_PRICE_PLAN_MAP", "")
        or _get_keyring_value("stripe_price_plan_map")
    )
    mapping: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        pid, _, plan = entry.partition(":")
        pid, plan = pid.strip(), plan.strip().lower()
        if pid and plan in {"ultra", "pro", "free"}:
            mapping[pid] = plan
    return mapping


def _get_allowed_checkout_origins() -> set[str]:
    raw = os.environ.get("LEXA_ALLOWED_CHECKOUT_ORIGINS", "") or os.environ.get("LEXA_APP_URL", "")
    origins = {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}
    if os.environ.get("APP_URL"):
        origins.add(os.environ["APP_URL"].strip().rstrip("/"))
    return origins


def _origin_from_url(raw_url: str) -> str:
    parsed = urlparse(raw_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _validate_checkout_request(req: "CheckoutRequest") -> JSONResponse | None:
    if not _PRICE_ID_RE.match(req.price_id or ""):
        return JSONResponse(status_code=400, content={"error": "Invalid Stripe price id."})

    allowed_prices = _get_allowed_price_ids()
    if not allowed_prices:
        return JSONResponse(status_code=503, content={"error": "Stripe price allowlist is not configured."})
    if req.price_id not in allowed_prices:
        audit_log("stripe_checkout", "price_denied", req.price_id[:40])
        return JSONResponse(status_code=403, content={"error": "Stripe price is not allowed."})

    allowed_origins = _get_allowed_checkout_origins()
    if not allowed_origins:
        return JSONResponse(status_code=503, content={"error": "Checkout redirect origins are not configured."})
    for raw_url in (req.success_url, req.cancel_url):
        origin = _origin_from_url(raw_url)
        if not origin or origin not in allowed_origins:
            audit_log("stripe_checkout", "redirect_denied", origin or "invalid")
            return JSONResponse(status_code=400, content={"error": "Checkout redirect URL is not allowed."})
    return None


def _supabase_request(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{_get_supabase_url()}{path}"
    response = requests.request(method, url, timeout=12, **kwargs)
    if response.status_code >= 400:
        logger.warning("Supabase request failed: %s %s -> %s", method, path, response.status_code)
    response.raise_for_status()
    return response


def _fetch_supabase_user(access_token: str) -> dict[str, Any] | None:
    auth_key = _supabase_auth_key()
    if not _get_supabase_url() or not auth_key:
        return None
    response = _supabase_request(
        "GET",
        "/auth/v1/user",
        headers={
            "apikey": auth_key,
            "Authorization": f"Bearer {access_token}",
        },
    )
    data = response.json()
    if not data.get("id"):
        return None
    return data


async def _require_supabase_user(request: Request, body_user_id: str = "", body_email: str = "") -> tuple[dict | None, JSONResponse | None]:
    if not _get_supabase_url() or not _supabase_auth_key():
        return None, JSONResponse(status_code=503, content={"error": "Supabase auth is not configured."})

    token = _extract_bearer_token(request)
    if not token:
        return None, JSONResponse(status_code=401, content={"error": "Missing bearer token."})

    try:
        user = await asyncio.to_thread(_fetch_supabase_user, token)
    except requests.HTTPError:
        return None, JSONResponse(status_code=401, content={"error": "Invalid bearer token."})
    except requests.RequestException:
        return None, JSONResponse(status_code=502, content={"error": "Supabase auth check failed."})

    if not user:
        return None, JSONResponse(status_code=401, content={"error": "Invalid bearer token."})

    user_id = str(user.get("id") or "")
    email = str(user.get("email") or "")
    if body_user_id and body_user_id != user_id:
        audit_log("stripe_checkout", "user_id_mismatch", body_user_id[:40])
        return None, JSONResponse(status_code=403, content={"error": "Authenticated user mismatch."})
    if body_email and email and body_email.lower() != email.lower():
        audit_log("stripe_checkout", "email_mismatch", body_email[:80])
        return None, JSONResponse(status_code=403, content={"error": "Authenticated email mismatch."})
    return user, None


# ── SQLite Subscriptions DB ──────────────────────
_SUBS_DB = LEXA_DATA_DIR / "lexa_subscriptions.db"
_db_initialized = False


def _get_db() -> sqlite3.Connection:
    """Get SQLite connection for subscriptions DB."""
    global _db_initialized
    conn = sqlite3.connect(str(_SUBS_DB), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if not _db_initialized:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id TEXT PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                status TEXT NOT NULL DEFAULT 'inactive',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                license_key TEXT UNIQUE,
                price_id TEXT,
                current_period_start TEXT,
                current_period_end TEXT,
                cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migration fuer bestehende DBs: Spalten ergaenzen, falls die Tabelle aus
        # einer aelteren Version stammt (SQLite kennt kein "ADD COLUMN IF NOT EXISTS").
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(subscriptions)")}
        if "price_id" not in existing_cols:
            conn.execute("ALTER TABLE subscriptions ADD COLUMN price_id TEXT")
        if "current_period_start" not in existing_cols:
            conn.execute("ALTER TABLE subscriptions ADD COLUMN current_period_start TEXT")
        if "cancel_at_period_end" not in existing_cols:
            conn.execute(
                "ALTER TABLE subscriptions ADD COLUMN cancel_at_period_end INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subs_stripe_customer
            ON subscriptions(stripe_customer_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subs_license_key
            ON subscriptions(license_key)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subs_status
            ON subscriptions(status)
        """)
        conn.commit()
        _db_initialized = True
    return conn


def _generate_license_key(user_id: str, subscription_id: str) -> str:
    """Generate a deterministic license key from user_id + subscription_id."""
    salt = os.environ.get("STRIPE_SECRET_KEY", "")
    if not salt:
        salt = _get_supabase_service_role_key()
    if not salt:
        # Local-only fallback for development when no SaaS secrets are configured.
        salt = "lexa-local-development"
    raw = f"{user_id}:{subscription_id}:{salt}"
    h = hashlib.sha256(raw.encode()).hexdigest()
    # Format: LEXA-XXXXX-XXXXX-XXXXX-XXXXX
    parts = [h[i:i + 5].upper() for i in range(0, 20, 5)]
    return f"LEXA-{'-'.join(parts)}"


# ── Request/Response Models ───────────────────────

class CheckoutRequest(BaseModel):
    price_id: str
    user_id: str = ""
    email: str = ""
    success_url: str
    cancel_url: str


class PortalRequest(BaseModel):
    user_id: str = ""


class LicenseValidateRequest(BaseModel):
    license_key: str = Field(..., min_length=1, max_length=64)


def _normalize_subscription_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in _KNOWN_SUBSCRIPTION_STATUSES:
        return normalized
    return "canceled"


def _price_id_from_subscription(subscription) -> str:
    try:
        if isinstance(subscription, dict):
            items = subscription.get("items", {}).get("data", [])
        else:
            items = subscription.get("items", {}).get("data", []) if hasattr(subscription, "get") else subscription.items.data
        if not items:
            return ""
        item = items[0] if isinstance(items, list) else items
        price = item.get("price", {}) if isinstance(item, dict) else item.price
        return price.get("id", "") if isinstance(price, dict) else str(price.id or "")
    except Exception:
        return ""


def _subscription_field(subscription, field: str):
    """Read a field from a Stripe subscription object (dict or SDK object)."""
    try:
        if isinstance(subscription, dict):
            return subscription.get(field)
        if hasattr(subscription, "get"):
            return subscription.get(field)
        return getattr(subscription, field, None)
    except Exception:
        return None


def _subscription_first_item(subscription):
    """Return the first subscription item (dict or SDK object), if available."""
    try:
        items = _subscription_field(subscription, "items")
        if items is None:
            return None
        data = items.get("data", []) if isinstance(items, dict) else getattr(items, "data", [])
        if not data:
            return None
        return data[0]
    except Exception:
        return None


def _subscription_period_value(subscription, field: str):
    """Read a period timestamp, preferring the item-level field (Stripe API 2025-*).

    Aktuelle Stripe-API-Versionen verschieben current_period_start/-end von der
    Subscription auf die Subscription-Items. Wir lesen daher zuerst vom ersten Item
    und fallen auf das Top-Level-Feld zurueck (aeltere API-Versionen).
    """
    item = _subscription_first_item(subscription)
    if item is not None:
        value = item.get(field) if isinstance(item, dict) else getattr(item, field, None)
        if value:
            return value
    return _subscription_field(subscription, field)


def _subscription_period_start(subscription) -> str | None:
    try:
        value = _subscription_period_value(subscription, "current_period_start")
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat() if value else None
    except Exception:
        return None


def _subscription_period_end(subscription) -> str | None:
    try:
        value = _subscription_period_value(subscription, "current_period_end")
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat() if value else None
    except Exception:
        return None


def _subscription_cancel_at_period_end(subscription) -> bool:
    try:
        value = subscription.get("cancel_at_period_end") if isinstance(subscription, dict) else subscription.cancel_at_period_end
        return bool(value)
    except Exception:
        return False


def _subscription_customer_id(subscription, fallback: str = "") -> str:
    try:
        value = subscription.get("customer") if isinstance(subscription, dict) else subscription.customer
        return str(value or fallback or "")
    except Exception:
        return fallback


def _subscription_id(subscription) -> str:
    try:
        value = subscription.get("id") if isinstance(subscription, dict) else subscription.id
        return str(value or "")
    except Exception:
        return ""


def _subscription_status(subscription) -> str:
    try:
        value = subscription.get("status") if isinstance(subscription, dict) else subscription.status
        return _normalize_subscription_status(str(value or ""))
    except Exception:
        return "canceled"


def _supabase_upsert_subscription(user_id: str, customer_id: str, subscription) -> None:
    subscription_id = _subscription_id(subscription)
    if not user_id or not subscription_id:
        raise ValueError("Missing user_id or subscription_id")

    plan = _extract_plan_name(subscription)
    status = _subscription_status(subscription)
    payload = {
        "user_id": user_id,
        "plan": plan,
        "status": status,
        "stripe_customer_id": _subscription_customer_id(subscription, customer_id),
        "stripe_subscription_id": subscription_id,
        "price_id": _price_id_from_subscription(subscription),
        "current_period_start": _subscription_period_start(subscription),
        "current_period_end": _subscription_period_end(subscription),
        "cancel_at_period_end": _subscription_cancel_at_period_end(subscription),
    }

    _supabase_request(
        "POST",
        "/rest/v1/subscriptions?on_conflict=stripe_subscription_id",
        headers=_supabase_service_headers("resolution=merge-duplicates"),
        json=payload,
    )
    _supabase_request(
        "PATCH",
        f"/rest/v1/profiles?id=eq.{user_id}",
        headers=_supabase_service_headers(),
        json={"plan": plan if status in _ACTIVE_SUBSCRIPTION_STATUSES else "free"},
    )


def _supabase_mark_subscription_canceled(subscription_id: str) -> None:
    if not subscription_id:
        return
    user_id = _lookup_supabase_user_id_for_subscription(subscription_id)
    _supabase_request(
        "PATCH",
        f"/rest/v1/subscriptions?stripe_subscription_id=eq.{subscription_id}",
        headers=_supabase_service_headers(),
        json={"status": "canceled", "cancel_at_period_end": True},
    )
    if not user_id:
        return
    response = _supabase_request(
        "GET",
        f"/rest/v1/subscriptions?user_id=eq.{user_id}&status=in.(active,trialing)&select=plan&limit=1",
        headers=_supabase_service_headers(),
    )
    if not response.json():
        _supabase_request(
            "PATCH",
            f"/rest/v1/profiles?id=eq.{user_id}",
            headers=_supabase_service_headers(),
            json={"plan": "free"},
        )


# ── Endpoints ─────────────────────────────────────

def _lookup_supabase_user_id_for_subscription(subscription_id: str) -> str:
    if not subscription_id:
        return ""
    response = _supabase_request(
        "GET",
        f"/rest/v1/subscriptions?stripe_subscription_id=eq.{subscription_id}&select=user_id&limit=1",
        headers=_supabase_service_headers(),
    )
    rows = response.json()
    if not rows:
        return ""
    return str(rows[0].get("user_id") or "")


def _sqlite_upsert_subscription(user_id: str, customer_id: str, subscription) -> None:
    subscription_id = _subscription_id(subscription)
    plan = _extract_plan_name(subscription)
    status = _subscription_status(subscription)
    price_id = _price_id_from_subscription(subscription)
    period_start = _subscription_period_start(subscription)
    period_end = _subscription_period_end(subscription)
    cancel_at_period_end = 1 if _subscription_cancel_at_period_end(subscription) else 0
    license_key = _generate_license_key(user_id, subscription_id)

    conn = _get_db()
    try:
        conn.execute("""
            INSERT INTO subscriptions (user_id, plan, status, stripe_customer_id,
                stripe_subscription_id, license_key, price_id, current_period_start,
                current_period_end, cancel_at_period_end, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                plan = excluded.plan,
                status = excluded.status,
                stripe_customer_id = excluded.stripe_customer_id,
                stripe_subscription_id = excluded.stripe_subscription_id,
                license_key = excluded.license_key,
                price_id = excluded.price_id,
                current_period_start = excluded.current_period_start,
                current_period_end = excluded.current_period_end,
                cancel_at_period_end = excluded.cancel_at_period_end,
                updated_at = datetime('now')
        """, (user_id, plan, status, customer_id, subscription_id, license_key,
              price_id, period_start, period_end, cancel_at_period_end))
        conn.commit()
    finally:
        conn.close()


def _sqlite_update_subscription(subscription) -> None:
    subscription_id = _subscription_id(subscription)
    plan = _extract_plan_name(subscription)
    status = _subscription_status(subscription)
    price_id = _price_id_from_subscription(subscription)
    period_start = _subscription_period_start(subscription)
    period_end = _subscription_period_end(subscription)
    cancel_at_period_end = 1 if _subscription_cancel_at_period_end(subscription) else 0

    conn = _get_db()
    try:
        conn.execute("""
            UPDATE subscriptions
            SET plan = ?, status = ?, price_id = ?, current_period_start = ?,
                current_period_end = ?, cancel_at_period_end = ?, updated_at = datetime('now')
            WHERE stripe_subscription_id = ?
        """, (plan, status, price_id, period_start, period_end,
              cancel_at_period_end, subscription_id))
        conn.commit()
    finally:
        conn.close()


def _sqlite_mark_subscription_canceled(subscription_id: str) -> None:
    conn = _get_db()
    try:
        conn.execute("""
            UPDATE subscriptions
            SET status = 'canceled', updated_at = datetime('now')
            WHERE stripe_subscription_id = ?
        """, (subscription_id,))
        conn.commit()
    finally:
        conn.close()


def _sqlite_get_subscription(user_id: str) -> dict | None:
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _sqlite_validate_license(license_key: str) -> dict | None:
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE license_key = ?", (license_key,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _supabase_get_subscription_for_user(user_id: str) -> dict | None:
    response = _supabase_request(
        "GET",
        f"/rest/v1/subscriptions?user_id=eq.{user_id}&select=*&order=current_period_end.desc.nullslast&limit=1",
        headers=_supabase_service_headers(),
    )
    rows = response.json()
    return rows[0] if rows else None


def _supabase_validate_license(license_key: str) -> dict | None:
    response = _supabase_request(
        "GET",
        f"/rest/v1/profiles?license_key=eq.{license_key}&select=id,plan,license_key&limit=1",
        headers=_supabase_service_headers(),
    )
    profiles = response.json()
    if not profiles:
        return None

    profile = profiles[0]
    user_id = profile.get("id")
    subscription = _supabase_get_subscription_for_user(user_id)
    if not subscription:
        return {
            "plan": profile.get("plan", "free"),
            "status": "inactive",
            "current_period_end": None,
        }
    return subscription


@router.post("/stripe/checkout")
async def create_checkout_session(req: CheckoutRequest, request: Request):
    """Create a Stripe Checkout Session for subscription purchase."""
    if not check_rate_limit("chat"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})

    invalid = _validate_checkout_request(req)
    if invalid is not None:
        return invalid

    user, auth_error = await _require_supabase_user(request, req.user_id, req.email)
    if auth_error is not None:
        return auth_error

    user_id = str(user.get("id", ""))
    email = str(user.get("email") or req.email or "")
    if not user_id or not email:
        return JSONResponse(status_code=400, content={"error": "Authenticated user has no usable email."})

    audit_log("stripe_checkout", "attempt", user_id)

    try:
        _init_stripe()

        # Create or retrieve Stripe customer by email
        def _create_session():
            # Search for existing customer
            customers = stripe.Customer.list(email=email, limit=1)
            if customers.data:
                customer = customers.data[0]
            else:
                customer = stripe.Customer.create(
                    email=email,
                    metadata={"user_id": user_id},
                )

            # Create checkout session
            session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=["card"],
                mode="subscription",
                line_items=[{"price": req.price_id, "quantity": 1}],
                success_url=req.success_url,
                cancel_url=req.cancel_url,
                metadata={"user_id": user_id},
                client_reference_id=user_id,
            )
            return session

        session = await asyncio.to_thread(_create_session)
        audit_log("stripe_checkout", "created", session.id)
        return {"session_id": session.id}

    except ValueError as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    except stripe.StripeError as e:
        logger.error(f"Stripe checkout error: {e}", exc_info=True)
        audit_log("stripe_checkout", "error", str(e))
        return JSONResponse(status_code=502, content={"error": f"Stripe error: {e.user_message or str(e)}"})
    except Exception as e:
        logger.error(f"Checkout error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")):
    """Handle Stripe webhook events (signature-verified)."""
    if not stripe_signature:
        return JSONResponse(status_code=400, content={"error": "Missing Stripe-Signature header"})

    webhook_secret = _get_webhook_secret()
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        # 503 statt 200: Stripe wertet 2xx als erfolgreiche Zustellung und wiederholt
        # nicht. Ohne Secret koennen wir die Signatur nicht pruefen, also signalisieren
        # wir einen voruebergehenden Fehler, damit Stripe das Event spaeter erneut zustellt.
        return JSONResponse(status_code=503, content={"error": "Webhook not configured"})

    # Read raw body for signature verification
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, webhook_secret
        )
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        audit_log("stripe_webhook", "signature_invalid")
        return JSONResponse(status_code=400, content={"error": "Invalid signature"})
    except Exception as e:
        logger.error(f"Webhook parse error: {e}", exc_info=True)
        return JSONResponse(status_code=400, content={"error": "Invalid payload"})

    event_type = event["type"]
    data = event["data"]["object"]
    audit_log("stripe_webhook", event_type, data.get("id", ""))

    try:
        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(data)
        elif event_type == "customer.subscription.updated":
            await _handle_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(data)
        else:
            logger.info(f"Unhandled Stripe event: {event_type}")
    except Exception as e:
        logger.error(f"Webhook handler error for {event_type}: {e}", exc_info=True)
        # 500 statt 200: Bei (oft transienten) Handler-Fehlern soll Stripe das Event
        # gemaess Retry-Policy erneut zustellen. Idempotenz ist durch die upsert-/
        # ON-CONFLICT-Logik gegeben, sodass Wiederholungen keine Duplikate erzeugen.
        return JSONResponse(status_code=500, content={"error": "Handler error"})

    return {"status": "ok"}


async def _handle_checkout_completed(session: dict):
    """Process successful checkout — create/update subscription record."""
    user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id", "")
    customer_id = session.get("customer", "")
    subscription_id = session.get("subscription", "")

    if not user_id or not subscription_id:
        logger.warning(f"Checkout completed but missing user_id or subscription_id: {session.get('id')}")
        return

    # Fetch subscription details from Stripe
    def _fetch_and_store():
        _init_stripe()
        sub = stripe.Subscription.retrieve(subscription_id)
        # Defense-in-Depth: Die abgerufene Subscription muss zum Customer der Session
        # gehoeren. Die Signaturpruefung garantiert nur die Echtheit des Events, nicht
        # die Bindung user_id<->subscription (die aus der Metadata stammt).
        if customer_id:
            sub_customer = _subscription_customer_id(sub)
            if sub_customer and sub_customer != customer_id:
                logger.error(
                    "Checkout customer mismatch: session customer %s != subscription customer %s (sub=%s)",
                    customer_id,
                    sub_customer,
                    subscription_id,
                )
                audit_log("stripe_webhook", "customer_mismatch", subscription_id[:40])
                return
        if _supabase_configured():
            _supabase_upsert_subscription(user_id, customer_id, sub)
        else:
            _sqlite_upsert_subscription(user_id, customer_id, sub)
        logger.info(
            "Subscription created for user %s: %s (%s)",
            user_id,
            _extract_plan_name(sub),
            _subscription_status(sub),
        )

    await asyncio.to_thread(_fetch_and_store)


async def _handle_subscription_updated(subscription: dict):
    """Process subscription update (plan change, renewal, etc.)."""
    def _update():
        subscription_id = _subscription_id(subscription)
        if _supabase_configured():
            user_id = _lookup_supabase_user_id_for_subscription(subscription_id)
            if user_id:
                _supabase_upsert_subscription(user_id, _subscription_customer_id(subscription), subscription)
            else:
                logger.warning("Subscription update ignored; no Supabase user for %s", subscription_id)
        else:
            _sqlite_update_subscription(subscription)
        logger.info(
            "Subscription updated: %s -> %s (%s)",
            subscription_id,
            _extract_plan_name(subscription),
            _subscription_status(subscription),
        )

    await asyncio.to_thread(_update)


async def _handle_subscription_deleted(subscription: dict):
    """Process subscription cancellation."""
    subscription_id = _subscription_id(subscription)

    def _delete():
        if _supabase_configured():
            _supabase_mark_subscription_canceled(subscription_id)
        else:
            _sqlite_mark_subscription_canceled(subscription_id)
        logger.info("Subscription canceled: %s", subscription_id)

    await asyncio.to_thread(_delete)


def _extract_plan_name(subscription) -> str:
    """Extract plan name from Stripe subscription object.

    Klassifiziert zuerst deterministisch ueber die price_id (explizite ENV-Map bzw.
    'pro'/'ultra'-Substring), erst danach ueber den OPTIONALEN nickname/product. Sonst
    wuerde ein fehlender nickname zahlende Kunden bei jeder Verlaengerung auf 'free'
    herabstufen (Webhook-product ist nur eine prod_-ID, nicht expandiert).
    """
    try:
        # 1) Deterministisch ueber die price_id (zuverlaessige, bereits allowlistete Quelle).
        price_id = _price_id_from_subscription(subscription)
        if price_id:
            mapped = _get_price_plan_map().get(price_id)
            if mapped:
                return mapped
            pid_l = price_id.lower()
            if "ultra" in pid_l:
                return "ultra"
            if "pro" in pid_l:
                return "pro"
        # 2) Fallback: optionaler nickname/product.
        if isinstance(subscription, dict):
            items = subscription.get("items", {}).get("data", [])
        else:
            items = subscription.get("items", {}).get("data", []) if hasattr(subscription, "get") else subscription.items.data
        if items:
            item = items[0] if isinstance(items, list) else items
            price = item.get("price", {}) if isinstance(item, dict) else item.price
            nickname = price.get("nickname", "") if isinstance(price, dict) else (price.nickname or "")
            # NUR der nickname taugt als Substring-Quelle. Die product-ID ist im Webhook
            # unexpandiert (prod_xyz) und enthaelt "pro" -> wuerde JEDEN Plan faelschlich als
            # "pro" einstufen (Gratis-Upgrade). Daher product NICHT mehr fuer die Klassifizierung.
            label = str(nickname or "").lower()
            if "ultra" in label:
                return "ultra"
            if "pro" in label:
                return "pro"
            logger.warning(
                "Could not classify plan from Stripe subscription (price_id=%s, nickname=%r); "
                "falling back to 'free'",
                _price_id_from_subscription(subscription),
                label.strip(),
            )
    except Exception as e:
        logger.warning(f"Could not extract plan name: {e}")
    # Bei nicht eindeutig erkennbarem Plan bewusst 'free' statt 'pro' zurueckgeben,
    # damit kein bezahltes Feature ohne passendes Produkt freigeschaltet wird.
    return "free"


@router.get("/stripe/subscription/{user_id}")
async def get_subscription(user_id: str, request: Request):
    """Get subscription status for a user."""
    if not check_rate_limit("stripe_read"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})
    if not _supabase_configured():
        return JSONResponse(status_code=503, content={"error": "Supabase subscription lookup is not configured."})

    user, auth_error = await _require_supabase_user(request, user_id, "")
    if auth_error is not None:
        return auth_error
    authenticated_user_id = str(user.get("id", ""))

    def _fetch():
        if _supabase_configured():
            return _supabase_get_subscription_for_user(authenticated_user_id)
        return _sqlite_get_subscription(authenticated_user_id)

    result = await asyncio.to_thread(_fetch)
    if not result:
        return {"plan": "free", "status": "inactive", "current_period_end": None}

    return {
        "plan": result.get("plan", "free"),
        "status": result.get("status", "inactive"),
        "current_period_end": result.get("current_period_end"),
    }


@router.post("/stripe/portal")
async def create_portal_session(req: PortalRequest, request: Request):
    """Create a Stripe Customer Portal session for subscription management."""
    if not check_rate_limit("chat"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})

    user, auth_error = await _require_supabase_user(request, req.user_id, "")
    if auth_error is not None:
        return auth_error
    user_id = str(user.get("id", ""))
    audit_log("stripe_portal", "attempt", user_id)

    def _fetch_customer_id():
        if _supabase_configured():
            row = _supabase_get_subscription_for_user(user_id)
            return row.get("stripe_customer_id") if row else None
        row = _sqlite_get_subscription(user_id)
        return row.get("stripe_customer_id") if row else None

    customer_id = await asyncio.to_thread(_fetch_customer_id)
    if not customer_id:
        return JSONResponse(status_code=404, content={"error": "No subscription found for user"})

    try:
        _init_stripe()

        def _create_portal():
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
            )
            return session.url

        portal_url = await asyncio.to_thread(_create_portal)
        audit_log("stripe_portal", "created", user_id)
        return {"url": portal_url}

    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}", exc_info=True)
        return JSONResponse(status_code=502, content={"error": f"Stripe error: {e.user_message or str(e)}"})
    except Exception as e:
        logger.error(f"Portal error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/license/validate")
async def validate_license(req: LicenseValidateRequest):
    """Validate a license key from the desktop app."""
    if not check_rate_limit("stripe_read"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})

    # Basic format validation
    normalized_key = (req.license_key or "").strip().upper()
    if not _LICENSE_KEY_RE.match(normalized_key):
        return {"valid": False, "error": "Invalid license key format"}

    def _validate():
        if _supabase_configured():
            return _supabase_validate_license(normalized_key)
        return _sqlite_validate_license(normalized_key)

    result = await asyncio.to_thread(_validate)
    if not result:
        return {"valid": False, "error": "License key not found"}

    status = result.get("status", "inactive")
    is_active = status in _ACTIVE_SUBSCRIPTION_STATUSES
    response = {
        "valid": is_active,
        "plan": result.get("plan", "free"),
        "status": status,
        "expires": result.get("current_period_end"),
    }
    # Bei Zahlungsproblemen einen differenzierten Grund mitliefern, damit das Frontend
    # ein ausstehendes Zahlungsproblem von einem ungueltigen/abgelaufenen Key
    # unterscheiden kann (bessere UX, weniger Support-Faelle).
    if not is_active and status in {"past_due", "unpaid"}:
        response["reason"] = "payment_failed"
    return response
