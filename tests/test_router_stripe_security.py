from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _reset_stripe_config(router_stripe, monkeypatch):
    for name in (
        "_stripe_key",
        "_webhook_secret",
        "_supabase_service_role_key",
        "_supabase_public_key",
        "_supabase_url",
    ):
        monkeypatch.setattr(router_stripe, name, None)


def test_extract_plan_name_classifies_by_price_id_without_nickname(monkeypatch):
    """Plan-Klassifizierung haengt an der price_id (zuverlaessig), nicht am optionalen nickname."""
    from backend import router_stripe

    # price_id mit 'ultra'-Substring, KEIN nickname -> trotzdem 'ultra' (kein Downgrade auf free)
    sub_ultra = {"items": {"data": [{"price": {"id": "price_ultra_monthly", "product": "prod_x"}}]}}
    assert router_stripe._extract_plan_name(sub_ultra) == "ultra"

    sub_pro = {"items": {"data": [{"price": {"id": "price_pro_monthly", "product": "prod_y"}}]}}
    assert router_stripe._extract_plan_name(sub_pro) == "pro"

    # Opake price_id ohne Substring -> explizite ENV-Map entscheidet deterministisch
    monkeypatch.setenv("STRIPE_PRICE_PLAN_MAP", "price_1AbcOpaque:ultra")
    sub_opaque = {"items": {"data": [{"price": {"id": "price_1AbcOpaque", "product": "prod_z"}}]}}
    assert router_stripe._extract_plan_name(sub_opaque) == "ultra"

    # Unbekannt + kein nickname/Map -> bewusst 'free'
    sub_unknown = {"items": {"data": [{"price": {"id": "price_1Unknown", "product": "prod_q"}}]}}
    assert router_stripe._extract_plan_name(sub_unknown) == "free"


def test_checkout_requires_price_allowlist_and_redirect_origin(monkeypatch):
    import backend.router_stripe as router_stripe

    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setenv("STRIPE_ALLOWED_PRICE_IDS", "price_pro_monthly")
    monkeypatch.setenv("LEXA_ALLOWED_CHECKOUT_ORIGINS", "https://exa-ai.space")

    good = router_stripe.CheckoutRequest(
        price_id="price_pro_monthly",
        success_url="https://exa-ai.space/dashboard.html?checkout=success",
        cancel_url="https://exa-ai.space/dashboard.html?checkout=cancel",
    )
    assert router_stripe._validate_checkout_request(good) is None

    bad_price = good.model_copy(update={"price_id": "price_other"})
    assert router_stripe._validate_checkout_request(bad_price).status_code == 403

    bad_redirect = good.model_copy(update={"success_url": "https://evil.example/ok"})
    assert router_stripe._validate_checkout_request(bad_redirect).status_code == 400


def test_checkout_uses_authenticated_supabase_user_not_client_identity(monkeypatch):
    import backend.router_stripe as router_stripe

    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fixture")
    monkeypatch.setenv("STRIPE_ALLOWED_PRICE_IDS", "price_pro_monthly")
    monkeypatch.setenv("LEXA_ALLOWED_CHECKOUT_ORIGINS", "https://exa-ai.space")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon_fixture")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service_fixture")
    monkeypatch.setattr(router_stripe, "check_rate_limit", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        router_stripe,
        "_fetch_supabase_user",
        lambda _token: {"id": "user-123", "email": "real@example.com"},
    )

    class FakeCustomer:
        @staticmethod
        def list(email, limit):
            assert email == "real@example.com"
            assert limit == 1
            return SimpleNamespace(data=[])

        @staticmethod
        def create(email, metadata):
            assert email == "real@example.com"
            assert metadata == {"user_id": "user-123"}
            return SimpleNamespace(id="cus_123")

    created = {}

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            created.update(kwargs)
            return SimpleNamespace(id="cs_test_123")

    monkeypatch.setattr(router_stripe.stripe, "Customer", FakeCustomer)
    monkeypatch.setattr(router_stripe.stripe, "checkout", SimpleNamespace(Session=FakeSession))

    app = FastAPI()
    app.include_router(router_stripe.router)
    client = TestClient(app)

    res = client.post(
        "/stripe/checkout",
        headers={"Authorization": "Bearer user-token"},
        json={
            "price_id": "price_pro_monthly",
            "user_id": "attacker-user",
            "email": "attacker@example.com",
            "success_url": "https://exa-ai.space/dashboard.html?checkout=success",
            "cancel_url": "https://exa-ai.space/dashboard.html?checkout=cancel",
        },
    )

    assert res.status_code == 403

    res = client.post(
        "/stripe/checkout",
        headers={"Authorization": "Bearer user-token"},
        json={
            "price_id": "price_pro_monthly",
            "success_url": "https://exa-ai.space/dashboard.html?checkout=success",
            "cancel_url": "https://exa-ai.space/dashboard.html?checkout=cancel",
        },
    )

    assert res.status_code == 200
    assert res.json() == {"session_id": "cs_test_123"}
    assert created["client_reference_id"] == "user-123"
    assert created["metadata"] == {"user_id": "user-123"}


def test_subscription_payload_normalizes_stripe_plan_status_and_profile_patch(monkeypatch):
    import backend.router_stripe as router_stripe

    calls = []

    def fake_supabase_request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("json")))
        return SimpleNamespace(status_code=200, json=lambda: [])

    monkeypatch.setattr(router_stripe, "_supabase_request", fake_supabase_request)
    monkeypatch.setattr(router_stripe, "_get_supabase_service_role_key", lambda: "service-key")
    monkeypatch.setattr(router_stripe, "_get_supabase_url", lambda: "https://project.supabase.co")

    subscription = {
        "id": "sub_123",
        "status": "active",
        "customer": "cus_123",
        "current_period_start": 1700000000,
        "current_period_end": 1701000000,
        "cancel_at_period_end": False,
        "items": {"data": [{"price": {"id": "price_ultra_monthly", "nickname": "Lexa Ultra"}}]},
    }

    router_stripe._supabase_upsert_subscription("user-123", "", subscription)

    upsert = calls[0]
    profile_patch = calls[1]
    assert upsert[0] == "POST"
    assert upsert[2]["plan"] == "ultra"
    assert upsert[2]["status"] == "active"
    assert upsert[2]["price_id"] == "price_ultra_monthly"
    assert profile_patch == ("PATCH", "/rest/v1/profiles?id=eq.user-123", {"plan": "ultra"})


def test_subscription_endpoint_requires_authenticated_user_and_hides_license(monkeypatch):
    import backend.router_stripe as router_stripe

    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon_fixture")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service_fixture")
    monkeypatch.setattr(router_stripe, "check_rate_limit", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        router_stripe,
        "_fetch_supabase_user",
        lambda _token: {"id": "user-123", "email": "real@example.com"},
    )
    monkeypatch.setattr(
        router_stripe,
        "_supabase_get_subscription_for_user",
        lambda user_id: {
            "plan": "pro",
            "status": "active",
            "current_period_end": "2026-12-31T00:00:00Z",
            "license_key": "LEXA-AAAAA-BBBBB-CCCCC-DDDDD",
        } if user_id == "user-123" else None,
    )

    app = FastAPI()
    app.include_router(router_stripe.router)
    client = TestClient(app)

    missing = client.get("/stripe/subscription/user-123")
    mismatch = client.get("/stripe/subscription/attacker", headers={"Authorization": "Bearer user-token"})
    ok = client.get("/stripe/subscription/user-123", headers={"Authorization": "Bearer user-token"})

    assert missing.status_code == 401
    assert mismatch.status_code == 403
    assert ok.status_code == 200
    assert ok.json() == {
        "plan": "pro",
        "status": "active",
        "current_period_end": "2026-12-31T00:00:00Z",
    }


def test_license_validation_uses_post_body_not_url_path(monkeypatch):
    import backend.router_stripe as router_stripe

    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setattr(router_stripe, "check_rate_limit", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(router_stripe, "_supabase_configured", lambda: False)
    monkeypatch.setattr(
        router_stripe,
        "_sqlite_validate_license",
        lambda key: {
            "plan": "pro",
            "status": "active",
            "current_period_end": "2026-12-31T00:00:00Z",
        } if key == "LEXA-AAAAA-BBBBB-CCCCC-DDDDD" else None,
    )

    app = FastAPI()
    app.include_router(router_stripe.router)
    client = TestClient(app)

    old_get = client.get("/license/validate/LEXA-AAAAA-BBBBB-CCCCC-DDDDD")
    posted = client.post("/license/validate", json={"license_key": "LEXA-AAAAA-BBBBB-CCCCC-DDDDD"})

    assert old_get.status_code == 404
    assert posted.status_code == 200
    assert posted.json()["valid"] is True
    assert posted.json()["plan"] == "pro"


def test_generated_license_key_matches_public_format(monkeypatch):
    import backend.router_stripe as router_stripe

    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fixture")

    key = router_stripe._generate_license_key("user-123", "sub-123")

    assert router_stripe._LICENSE_KEY_RE.match(key)


# ── Webhook-Signaturpruefung (Scan-Fix: war ungetestet) ──

def _webhook_client(router_stripe):
    app = FastAPI()
    app.include_router(router_stripe.router)
    return TestClient(app)


def test_webhook_missing_signature_header_is_rejected(monkeypatch):
    import backend.router_stripe as router_stripe
    _reset_stripe_config(router_stripe, monkeypatch)
    client = _webhook_client(router_stripe)

    res = client.post("/stripe/webhook", content=b"{}")
    assert res.status_code == 400
    assert "Stripe-Signature" in res.json()["error"]


def test_webhook_without_configured_secret_returns_503_not_200(monkeypatch):
    # Wichtig: KEIN 2xx ohne Secret, sonst quittiert Stripe das Event als zugestellt.
    import backend.router_stripe as router_stripe
    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setattr(router_stripe, "_get_webhook_secret", lambda: "")
    client = _webhook_client(router_stripe)

    res = client.post("/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "t=1,v1=abc"})
    assert res.status_code == 503


def test_webhook_invalid_signature_is_rejected(monkeypatch):
    import backend.router_stripe as router_stripe
    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setattr(router_stripe, "_get_webhook_secret", lambda: "whsec_test")

    def _raise(*a, **k):
        raise router_stripe.stripe.SignatureVerificationError("bad", "sig")

    monkeypatch.setattr(router_stripe.stripe.Webhook, "construct_event", _raise)
    monkeypatch.setattr(router_stripe, "audit_log", lambda *a, **k: None)
    client = _webhook_client(router_stripe)

    res = client.post("/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "bad"})
    assert res.status_code == 400
    assert res.json()["error"] == "Invalid signature"


def test_webhook_malformed_payload_is_rejected(monkeypatch):
    import backend.router_stripe as router_stripe
    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setattr(router_stripe, "_get_webhook_secret", lambda: "whsec_test")
    monkeypatch.setattr(router_stripe.stripe.Webhook, "construct_event",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    monkeypatch.setattr(router_stripe, "audit_log", lambda *a, **k: None)
    client = _webhook_client(router_stripe)

    res = client.post("/stripe/webhook", content=b"not-json", headers={"Stripe-Signature": "x"})
    assert res.status_code == 400
    assert res.json()["error"] == "Invalid payload"


def test_webhook_valid_event_dispatches_handler(monkeypatch):
    import backend.router_stripe as router_stripe
    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setattr(router_stripe, "_get_webhook_secret", lambda: "whsec_test")
    monkeypatch.setattr(router_stripe.stripe.Webhook, "construct_event",
                        lambda *a, **k: {"type": "checkout.session.completed",
                                          "data": {"object": {"id": "cs_1"}}})
    monkeypatch.setattr(router_stripe, "audit_log", lambda *a, **k: None)
    handled = {}

    async def _fake_handler(data):
        handled["data"] = data

    monkeypatch.setattr(router_stripe, "_handle_checkout_completed", _fake_handler)
    client = _webhook_client(router_stripe)

    res = client.post("/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert handled["data"]["id"] == "cs_1"


def test_webhook_handler_error_returns_500_for_stripe_retry(monkeypatch):
    import backend.router_stripe as router_stripe
    _reset_stripe_config(router_stripe, monkeypatch)
    monkeypatch.setattr(router_stripe, "_get_webhook_secret", lambda: "whsec_test")
    monkeypatch.setattr(router_stripe.stripe.Webhook, "construct_event",
                        lambda *a, **k: {"type": "customer.subscription.updated",
                                          "data": {"object": {"id": "sub_1"}}})
    monkeypatch.setattr(router_stripe, "audit_log", lambda *a, **k: None)

    async def _boom(data):
        raise RuntimeError("db down")

    monkeypatch.setattr(router_stripe, "_handle_subscription_updated", _boom)
    client = _webhook_client(router_stripe)

    res = client.post("/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "ok"})
    assert res.status_code == 500
