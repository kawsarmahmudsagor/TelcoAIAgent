"""Maps typed BSS errors onto HTTP errors, shared by the portal routes."""

from fastapi import HTTPException

from app.bss.errors import BssError

_STATUS_BY_CODE: dict[str, int] = {
    "subscriber_not_found": 404,
    "package_not_found": 404,
    "case_not_found": 404,
    "incident_not_found": 404,
    "notification_not_found": 404,
    "no_pending_action": 404,
    "insufficient_balance": 409,
    "insufficient_points": 409,
    "offer_not_eligible": 409,
    "limit_exceeded": 422,
    "invalid_msisdn": 422,
    "invalid_request": 422,
    "otp_invalid": 400,
    "otp_expired": 410,
    "otp_attempts_exceeded": 429,
    "too_many_codes": 429,
}


def bss_http_error(e: BssError) -> HTTPException:
    return HTTPException(
        _STATUS_BY_CODE.get(e.code, 400), detail={"code": e.code, "message": e.message}
    )
