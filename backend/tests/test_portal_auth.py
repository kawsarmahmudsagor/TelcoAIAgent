from datetime import datetime, timedelta, timezone

from jose import jwt

from app.api.deps import PORTAL_COOKIE
from app.config import get_settings
from app.services.auth_service import create_access_token, decode_access_token

PERSONA_MSISDNS = ["01712342841", "01812347392", "01912345501", "01612341109", "01512346620"]


def test_personas_lists_seeded_five_in_order(anon_api):
    r = anon_api.get("/api/demo/personas")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    cards = r.json()
    assert [c["msisdn"] for c in cards] == PERSONA_MSISDNS
    assert all(c["headline"] for c in cards)
    assert cards[0]["masked_msisdn"] == "017••••2841"


def test_login_sets_portal_cookie_and_me_works(anon_api):
    r = anon_api.post("/api/demo/login", json={"msisdn": "01712342841"})
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "Samiha Khan"
    assert body["first_name"] == "Samiha"
    assert PORTAL_COOKIE in r.cookies
    me = anon_api.get("/api/me")
    assert me.status_code == 200
    assert me.json()["subscriber_id"] == body["subscriber_id"]


def test_login_unknown_or_non_persona_msisdn_404(anon_api, bss_world):
    sub = bss_world.subscriber()
    assert anon_api.post("/api/demo/login", json={"msisdn": "01700000000"}).status_code == 404
    assert anon_api.post("/api/demo/login", json={"msisdn": sub.msisdn}).status_code == 404


def test_customer_token_refused_on_admin_route(anon_api):
    r = anon_api.post("/api/demo/login", json={"msisdn": "01712342841"})
    anon_api.cookies.set("session", r.cookies[PORTAL_COOKIE])
    assert anon_api.get("/api/conversations").status_code == 401


def test_admin_token_refused_on_me(anon_api):
    anon_api.cookies.set(PORTAL_COOKIE, create_access_token("ceo"))
    assert anon_api.get("/api/me").status_code == 401


def test_role_less_token_is_admin():
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = jwt.encode({"sub": "ceo", "exp": exp}, get_settings().jwt_secret, algorithm="HS256")
    claims = decode_access_token(token)
    assert claims.sub == "ceo" and claims.role == "admin"


def test_logout_clears_cookie(anon_api):
    anon_api.post("/api/demo/login", json={"msisdn": "01712342841"})
    assert anon_api.get("/api/me").status_code == 200
    r = anon_api.post("/api/demo/logout")
    assert r.json() == {"ok": True}
    assert anon_api.get("/api/me").status_code == 401
