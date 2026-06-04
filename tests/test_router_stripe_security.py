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
