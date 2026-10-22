import pytest

from app.api.bss_http import bss_http_error
from app.bss import errors

CASES = [
    (errors.SubscriberNotFound, 404),
    (errors.PackageNotFound, 404),
    (errors.CaseNotFound, 404),
    (errors.NoPendingAction, 404),
    (errors.InsufficientBalance, 409),
    (errors.InsufficientPoints, 409),
    (errors.OfferNotEligible, 409),
    (errors.LimitExceeded, 422),
    (errors.InvalidMsisdn, 422),
    (errors.InvalidRequest, 422),
    (errors.OtpInvalid, 400),
    (errors.OtpExpired, 410),
    (errors.OtpAttemptsExceeded, 429),
    (errors.BssError, 400),
]


@pytest.mark.parametrize("cls,status", CASES)
def test_status_and_detail(cls, status):
    exc = bss_http_error(cls("boom"))
    assert exc.status_code == status
    assert exc.detail == {"code": cls.code, "message": "boom"}
