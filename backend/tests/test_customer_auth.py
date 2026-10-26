from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.api.deps import PORTAL_COOKIE
from app.bss import otp
from app.bss.clock import utc_now
from app.bss.registration import WELCOME_BALANCE, WELCOME_CODE, WELCOME_DATA_MB
from app.models.telco import Balance, Package, Subscriber, Subscription, SubscriptionStatus

NEW_MSISDN = "01999888001"
PASSWORD = "s3cret-pass"


def _signup(client, **o):
    body = {
        "full_name": "Test Signup",
        "msisdn": NEW_MSISDN,
        "district": "Dhaka",
        "plan_type": "prepaid",
        "password": PASSWORD,
    } | o
    return client.post("/api/auth/customer/signup", json=body)


def test_signup_creates_subscriber_with_welcome_bonus(anon_api, bss_world, db):
    r = _signup(anon_api)
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["full_name"] == "Test Signup" and body["msisdn"] == NEW_MSISDN
    assert PORTAL_COOKIE in r.cookies
    assert anon_api.get("/api/me").json()["subscriber_id"] == body["subscriber_id"]

    sub = db.scalar(select(Subscriber).where(Subscriber.msisdn == NEW_MSISDN))
    assert sub.password_hash and PASSWORD not in sub.password_hash
    assert db.get(Balance, sub.id).main_balance == WELCOME_BALANCE == Decimal("200")
    subs = db.scalars(select(Subscription).where(Subscription.subscriber_id == sub.id)).all()
    assert len(subs) == 1
    welcome = subs[0]
    assert welcome.data_left_mb == WELCOME_DATA_MB == 5120
    assert welcome.status == SubscriptionStatus.active
    assert welcome.expires_at - welcome.activated_at == timedelta(days=7)
    pkg = db.get(Package, welcome.package_id)
    assert pkg.code == WELCOME_CODE and pkg.is_active is False


def test_signup_duplicate_msisdn_409(anon_api, bss_world):
    assert _signup(anon_api).status_code == 201
    r = _signup(anon_api, full_name="Someone Else")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "msisdn_taken"


def test_signup_validation_422(anon_api, bss_world):
    assert _signup(anon_api, msisdn="0199988800").status_code == 422
    assert _signup(anon_api, msisdn="02999888001").status_code == 422
    assert _signup(anon_api, password="short").status_code == 422
    assert _signup(anon_api, full_name=" ").status_code == 422
    assert _signup(anon_api, plan_type="free").status_code == 422


def test_password_login(anon_api, bss_world):
    _signup(anon_api)
    anon_api.post("/api/demo/logout")
    assert anon_api.get("/api/me").status_code == 401
    r = anon_api.post(
        "/api/auth/customer/login", json={"msisdn": NEW_MSISDN, "password": PASSWORD}
    )
    assert r.status_code == 200
    assert r.json()["msisdn"] == NEW_MSISDN
    assert anon_api.get("/api/me").status_code == 200


def test_password_login_failures_look_the_same(anon_api, bss_world):
    _signup(anon_api)
    anon_api.post("/api/demo/logout")
    no_password = bss_world.subscriber()
    for msisdn, password in [
        (NEW_MSISDN, "wrong-password"),
        ("01999888999", PASSWORD),
        (no_password.msisdn, PASSWORD),
    ]:
        r = anon_api.post(
            "/api/auth/customer/login", json={"msisdn": msisdn, "password": password}
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "invalid_credentials"
    assert anon_api.get("/api/me").status_code == 401


def _reset_start(client, msisdn):
    return client.post("/api/auth/customer/reset/start", json={"msisdn": msisdn})


def _reset_confirm(client, msisdn, start, code=None, password="brand-new-pass"):
    return client.post(
        "/api/auth/customer/reset/confirm",
        json={
            "msisdn": msisdn,
            "reset_id": start["reset_id"],
            "code": code or start["otp"]["code"],
            "new_password": password,
        },
    )


def test_reset_sets_password_and_logs_in(anon_api, bss_world):
    sub = bss_world.subscriber()
    r = _reset_start(anon_api, sub.msisdn)
    assert r.status_code == 200
    start = r.json()
    assert start["otp"]["to"] == f"{sub.msisdn[:3]}••••{sub.msisdn[-4:]}"
    assert len(start["otp"]["code"]) == 6

    r = _reset_confirm(anon_api, sub.msisdn, start)
    assert r.status_code == 200
    assert r.json()["subscriber_id"] == str(sub.id)
    assert anon_api.get("/api/me").status_code == 200

    anon_api.post("/api/demo/logout")
    ok = anon_api.post(
        "/api/auth/customer/login", json={"msisdn": sub.msisdn, "password": "brand-new-pass"}
    )
    assert ok.status_code == 200
    # The code is single-use.
    again = _reset_confirm(anon_api, sub.msisdn, start, password="another-pass")
    assert again.status_code == 400


def test_reset_unknown_number_404(anon_api, bss_world):
    r = _reset_start(anon_api, "01999888999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "subscriber_not_found"


def test_reset_wrong_code_400_and_password_unchanged(anon_api, bss_world):
    _signup(anon_api)
    anon_api.post("/api/demo/logout")
    start = _reset_start(anon_api, NEW_MSISDN).json()
    wrong = "000000" if start["otp"]["code"] != "000000" else "111111"
    r = _reset_confirm(anon_api, NEW_MSISDN, start, code=wrong)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "otp_invalid"
    assert anon_api.get("/api/me").status_code == 401
    ok = anon_api.post(
        "/api/auth/customer/login", json={"msisdn": NEW_MSISDN, "password": PASSWORD}
    )
    assert ok.status_code == 200


def test_reset_code_bound_to_number(anon_api, bss_world):
    a, b = bss_world.subscriber(), bss_world.subscriber()
    start = _reset_start(anon_api, a.msisdn).json()
    r = _reset_confirm(anon_api, b.msisdn, start)
    assert r.status_code == 404


def test_reset_expired_code_410(anon_api, bss_world, monkeypatch):
    sub = bss_world.subscriber()
    start = _reset_start(anon_api, sub.msisdn).json()
    later = utc_now() + otp.OTP_TTL + timedelta(seconds=5)
    monkeypatch.setattr(otp, "utc_now", lambda: later)
    r = _reset_confirm(anon_api, sub.msisdn, start)
    assert r.status_code == 410


def test_reset_throttled_after_five_codes(anon_api, bss_world):
    sub = bss_world.subscriber()
    for _ in range(otp.MAX_CODES_PER_WINDOW):
        assert _reset_start(anon_api, sub.msisdn).status_code == 200
    r = _reset_start(anon_api, sub.msisdn)
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "too_many_codes"


def test_reset_short_password_422(anon_api, bss_world):
    sub = bss_world.subscriber()
    start = _reset_start(anon_api, sub.msisdn).json()
    assert _reset_confirm(anon_api, sub.msisdn, start, password="short").status_code == 422
