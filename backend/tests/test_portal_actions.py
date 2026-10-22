from decimal import Decimal

from sqlalchemy import func, select

from app.models.telco import Actor, AuditEvent, Balance, Transaction

START = "/api/me/actions/start"
RECHARGE = {"kind": "recharge", "amount": 100, "channel": "bkash"}


def _confirm_url(action_id):
    return f"/api/me/actions/{action_id}/confirm"


def _start(client, action):
    r = client.post(START, json=action)
    assert r.status_code == 200, r.text
    return r.json()


def _txns(db, sub):
    db.rollback()
    return db.scalar(select(func.count()).select_from(Transaction).where(Transaction.subscriber_id == sub.id))


def _balance(db, sub):
    db.rollback()
    return db.scalar(select(Balance.main_balance).where(Balance.subscriber_id == sub.id))


def test_recharge_start_then_confirm_credits_balance(bss_world, customer_api, db):
    sub = bss_world.subscriber(main_balance=Decimal("50"))
    c = customer_api(sub.id)
    s = _start(c, RECHARGE)
    assert len(s["otp"]["code"]) == 6 and s["otp"]["code"].isdigit()
    assert s["kind"] == "recharge" and s["title"] == "Recharge ৳100"
    assert s["amount"] == 100 and s["pay_from"] == "bkash" and s["target"] == sub.msisdn
    assert s["otp"]["to"] != sub.msisdn
    r = c.post(_confirm_url(s["action_id"]), json={"action": RECHARGE, "code": s["otp"]["code"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ref"].startswith("TXN-") and body["kind"] == "recharge"
    assert body["main_balance"] == 150
    assert _balance(db, sub) == Decimal("150")


def test_purchase_from_balance(bss_world, customer_api, db):
    sub = bss_world.subscriber(main_balance=Decimal("500"))
    pkg = bss_world.package(price=Decimal("120"), name="PYTEST Pack")
    action = {"kind": "purchase", "package_code": pkg.code, "pay_from": "balance"}
    c = customer_api(sub.id)
    s = _start(c, action)
    assert s["title"] == "PYTEST Pack" and s["amount"] == 120 and s["pay_from"] == "balance"
    r = c.post(_confirm_url(s["action_id"]), json={"action": action, "code": s["otp"]["code"]})
    assert r.status_code == 200, r.text
    assert r.json()["main_balance"] == 380
    assert r.json()["ref"].startswith("TXN-")


def test_redeem_with_points(bss_world, customer_api):
    sub = bss_world.subscriber(reward_points=500)
    offer = bss_world.offer(points_cost=200)
    action = {"kind": "redeem", "offer_id": str(offer.id)}
    c = customer_api(sub.id)
    s = _start(c, action)
    assert s["points_cost"] == 200 and s["pay_from"] == "points" and s["title"] == offer.title
    r = c.post(_confirm_url(s["action_id"]), json={"action": action, "code": s["otp"]["code"]})
    assert r.status_code == 200, r.text
    assert r.json()["reward_points"] == 300


def test_confirm_with_changed_request_is_rejected(bss_world, customer_api, db):
    sub = bss_world.subscriber(main_balance=Decimal("0"))
    c = customer_api(sub.id)
    s = _start(c, RECHARGE)
    changed = {**RECHARGE, "amount": 1000}
    r = c.post(_confirm_url(s["action_id"]), json={"action": changed, "code": s["otp"]["code"]})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "otp_invalid"
    assert _txns(db, sub) == 0


def test_double_confirm_returns_same_ref(bss_world, customer_api, db):
    sub = bss_world.subscriber(main_balance=Decimal("0"))
    c = customer_api(sub.id)
    s = _start(c, RECHARGE)
    payload = {"action": RECHARGE, "code": s["otp"]["code"]}
    a = c.post(_confirm_url(s["action_id"]), json=payload).json()
    b = c.post(_confirm_url(s["action_id"]), json=payload).json()
    assert a["ref"] == b["ref"]
    assert _txns(db, sub) == 1


def test_wrong_code_three_times_locks(bss_world, customer_api):
    sub = bss_world.subscriber()
    c = customer_api(sub.id)
    s = _start(c, RECHARGE)
    bad = "000000" if s["otp"]["code"] != "000000" else "111111"
    url = _confirm_url(s["action_id"])
    codes = [c.post(url, json={"action": RECHARGE, "code": bad}).status_code for _ in range(3)]
    assert codes == [400, 400, 400]
    r = c.post(url, json={"action": RECHARGE, "code": s["otp"]["code"]})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "otp_attempts_exceeded"


def test_sixth_code_in_15_minutes_is_throttled(bss_world, customer_api):
    sub = bss_world.subscriber()
    c = customer_api(sub.id)
    for _ in range(5):
        _start(c, RECHARGE)
    r = c.post(START, json=RECHARGE)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_codes"


def test_insufficient_balance_is_409(bss_world, customer_api):
    sub = bss_world.subscriber(main_balance=Decimal("10"))
    pkg = bss_world.package(price=Decimal("120"))
    r = customer_api(sub.id).post(
        START, json={"kind": "purchase", "package_code": pkg.code, "pay_from": "balance"}
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "insufficient_balance"


def test_recharge_bad_target_is_422(bss_world, customer_api):
    sub = bss_world.subscriber()
    r = customer_api(sub.id).post(START, json={**RECHARGE, "target_msisdn": "0123"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_msisdn"


def test_bengali_digit_code_accepted(bss_world, customer_api):
    sub = bss_world.subscriber(main_balance=Decimal("0"))
    c = customer_api(sub.id)
    s = _start(c, RECHARGE)
    code = s["otp"]["code"]
    bengali = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
    spaced = code[:3].translate(bengali) + " " + code[3:].translate(bengali)
    r = c.post(_confirm_url(s["action_id"]), json={"action": RECHARGE, "code": spaced})
    assert r.status_code == 200, r.text


def test_portal_transaction_audit_actor_is_portal(bss_world, customer_api, db):
    sub = bss_world.subscriber(main_balance=Decimal("0"))
    c = customer_api(sub.id)
    s = _start(c, RECHARGE)
    c.post(_confirm_url(s["action_id"]), json={"action": RECHARGE, "code": s["otp"]["code"]})
    db.rollback()
    events = db.scalars(select(AuditEvent).where(AuditEvent.subscriber_id == sub.id)).all()
    assert events and {e.actor for e in events} == {Actor.portal}
