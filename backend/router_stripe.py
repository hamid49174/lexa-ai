"""Lexa AI — Stripe Payment Router
API Endpoints für Stripe-Zahlungsintegration (SaaS Website)
"""

import asyncio
import hashlib
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import socket

import stripe
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.security import check_rate_limit, audit_log

logger = logging.getLogger("lexa.stripe")
router = APIRouter(tags=["stripe"])

# ── Stripe Configuration ─────────────────────────
_stripe_key = None
_webhook_secret = None


def _get_stripe_key() -> str:
    """Get Stripe secret key from environment or keyring."""
    global _stripe_key
    if _stripe_key:
        return _stripe_key
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        try:
            import keyring
            key = keyring.get_password("lexa-ai", "stripe_secret_key") or ""
        except Exception:
            pass
    _stripe_key = key
    return key


def _get_webhook_secret() -> str:
    """Get Stripe webhook secret from environment or keyring."""
    global _webhook_secret
    if _webhook_secret:
        return _webhook_secret
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        try:
            import keyring
            secret = keyring.get_password("lexa-ai", "stripe_webhook_secret") or ""
        except Exception:
            pass
    _webhook_secret = secret
    return secret


def _init_stripe():
    """Initialize Stripe SDK with API key."""
    key = _get_stripe_key()
    if not key:
        raise ValueError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = key


# ── SQLite Subscriptions DB ──────────────────────
_DATA_DIR = Path(os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent)))
_SUBS_DB = _DATA_DIR / "lexa_subscriptions.db"
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
                current_period_end TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
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
        # Machine-specific fallback instead of static 'lexa' string
        salt = hashlib.sha256(
            f"{user_id}:{subscription_id}:{socket.gethostname()}".encode()
        ).hexdigest()[:20].upper()
    raw = f"{user_id}:{subscription_id}:{salt}"
    h = hashlib.sha256(raw.encode()).hexdigest()
    # Format: LEXA-XXXX-XXXX-XXXX-XXXX
    parts = [h[i:i + 4].upper() for i in range(0, 16, 4)]
    return f"LEXA-{'-'.join(parts)}"


# ── Request/Response Models ───────────────────────

class CheckoutRequest(BaseModel):
    price_id: str
    user_id: str
    email: str
    success_url: str
    cancel_url: str


class PortalRequest(BaseModel):
    user_id: str


# ── Endpoints ─────────────────────────────────────

@router.post("/stripe/checkout")
async def create_checkout_session(req: CheckoutRequest):
    """Create a Stripe Checkout Session for subscription purchase."""
    if not check_rate_limit("chat"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})

    audit_log("stripe_checkout", "attempt", req.email)

    try:
        _init_stripe()

        # Create or retrieve Stripe customer by email
        def _create_session():
            # Search for existing customer
            customers = stripe.Customer.list(email=req.email, limit=1)
            if customers.data:
                customer = customers.data[0]
            else:
                customer = stripe.Customer.create(
                    email=req.email,
                    metadata={"user_id": req.user_id},
                )

            # Create checkout session
            session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=["card"],
                mode="subscription",
                line_items=[{"price": req.price_id, "quantity": 1}],
                success_url=req.success_url,
                cancel_url=req.cancel_url,
                metadata={"user_id": req.user_id},
                client_reference_id=req.user_id,
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
        return JSONResponse(status_code=200, content={"error": "Webhook not configured"})

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
        return JSONResponse(status_code=200, content={"error": "Handler error"})

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
        plan = _extract_plan_name(sub)
        period_end = datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc).isoformat()
        license_key = _generate_license_key(user_id, subscription_id)

        conn = _get_db()
        try:
            conn.execute("""
                INSERT INTO subscriptions (user_id, plan, status, stripe_customer_id,
                    stripe_subscription_id, license_key, current_period_end, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    plan = excluded.plan,
                    status = excluded.status,
                    stripe_customer_id = excluded.stripe_customer_id,
                    stripe_subscription_id = excluded.stripe_subscription_id,
                    license_key = excluded.license_key,
                    current_period_end = excluded.current_period_end,
                    updated_at = datetime('now')
            """, (user_id, plan, sub.status, customer_id, subscription_id, license_key, period_end))
            conn.commit()
            logger.info(f"Subscription created for user {user_id}: {plan} ({sub.status})")
        finally:
            conn.close()

    await asyncio.to_thread(_fetch_and_store)


async def _handle_subscription_updated(subscription: dict):
    """Process subscription update (plan change, renewal, etc.)."""
    customer_id = subscription.get("customer", "")
    subscription_id = subscription.get("id", "")
    status = subscription.get("status", "")
    plan = _extract_plan_name(subscription)
    period_end = datetime.fromtimestamp(
        subscription.get("current_period_end", 0), tz=timezone.utc
    ).isoformat()

    def _update():
        conn = _get_db()
        try:
            conn.execute("""
                UPDATE subscriptions
                SET plan = ?, status = ?, current_period_end = ?, updated_at = datetime('now')
                WHERE stripe_subscription_id = ?
            """, (plan, status, period_end, subscription_id))
            conn.commit()
            logger.info(f"Subscription updated: {subscription_id} → {plan} ({status})")
        finally:
            conn.close()

    await asyncio.to_thread(_update)


async def _handle_subscription_deleted(subscription: dict):
    """Process subscription cancellation."""
    subscription_id = subscription.get("id", "")

    def _delete():
        conn = _get_db()
        try:
            conn.execute("""
                UPDATE subscriptions
                SET status = 'canceled', updated_at = datetime('now')
                WHERE stripe_subscription_id = ?
            """, (subscription_id,))
            conn.commit()
            logger.info(f"Subscription canceled: {subscription_id}")
        finally:
            conn.close()

    await asyncio.to_thread(_delete)


def _extract_plan_name(subscription) -> str:
    """Extract plan name from Stripe subscription object."""
    try:
        if isinstance(subscription, dict):
            items = subscription.get("items", {}).get("data", [])
        else:
            items = subscription.get("items", {}).get("data", []) if hasattr(subscription, "get") else subscription.items.data
        if items:
            item = items[0] if isinstance(items, list) else items
            price = item.get("price", {}) if isinstance(item, dict) else item.price
            product = price.get("product", "") if isinstance(price, dict) else price.product
            nickname = price.get("nickname", "") if isinstance(price, dict) else (price.nickname or "")
            if nickname:
                return nickname.lower()
            return str(product)
    except Exception as e:
        logger.warning(f"Could not extract plan name: {e}")
    return "pro"


@router.get("/stripe/subscription/{user_id}")
async def get_subscription(user_id: str):
    """Get subscription status for a user."""
    if not check_rate_limit("stripe_read"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})

    def _fetch():
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)
        finally:
            conn.close()

    result = await asyncio.to_thread(_fetch)
    if not result:
        return {"plan": "free", "status": "inactive", "current_period_end": None}

    return {
        "plan": result["plan"],
        "status": result["status"],
        "current_period_end": result["current_period_end"],
        "license_key": result.get("license_key"),
    }


@router.post("/stripe/portal")
async def create_portal_session(req: PortalRequest):
    """Create a Stripe Customer Portal session for subscription management."""
    if not check_rate_limit("chat"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})

    audit_log("stripe_portal", "attempt", req.user_id)

    def _fetch_customer_id():
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT stripe_customer_id FROM subscriptions WHERE user_id = ?",
                (req.user_id,)
            ).fetchone()
            return row["stripe_customer_id"] if row else None
        finally:
            conn.close()

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
        audit_log("stripe_portal", "created", req.user_id)
        return {"url": portal_url}

    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}", exc_info=True)
        return JSONResponse(status_code=502, content={"error": f"Stripe error: {e.user_message or str(e)}"})
    except Exception as e:
        logger.error(f"Portal error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/license/validate/{license_key}")
async def validate_license(license_key: str):
    """Validate a license key from the desktop app."""
    if not check_rate_limit("stripe_read"):
        return JSONResponse(status_code=429, content={"error": "Rate limit erreicht."})

    # Basic format validation
    if not license_key or len(license_key) > 30:
        return {"valid": False, "error": "Invalid license key format"}

    def _validate():
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE license_key = ?", (license_key,)
            ).fetchone()
            if not row:
                return None
            return dict(row)
        finally:
            conn.close()

    result = await asyncio.to_thread(_validate)
    if not result:
        return {"valid": False, "error": "License key not found"}

    is_active = result["status"] in ("active", "trialing")
    return {
        "valid": is_active,
        "plan": result["plan"],
        "status": result["status"],
        "expires": result["current_period_end"],
    }
