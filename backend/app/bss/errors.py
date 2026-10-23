"""Typed BSS errors. `code` is stable (snake_case of the class name); `message`
is English for logs. Callers map `code` to user-facing text."""


class BssError(Exception):
    code: str = "bss_error"
    default_message: str = "BSS error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class SubscriberNotFound(BssError):
    code = "subscriber_not_found"
    default_message = "Subscriber not found"


class InsufficientBalance(BssError):
    code = "insufficient_balance"
    default_message = "Main balance is too low"


class PackageNotFound(BssError):
    code = "package_not_found"
    default_message = "Package not found"


class LimitExceeded(BssError):
    code = "limit_exceeded"
    default_message = "Transaction limit exceeded"


class InvalidMsisdn(BssError):
    code = "invalid_msisdn"
    default_message = "Invalid mobile number"


class OtpExpired(BssError):
    code = "otp_expired"
    default_message = "The code has expired"


class OtpInvalid(BssError):
    code = "otp_invalid"
    default_message = "The code is incorrect"


class OtpAttemptsExceeded(BssError):
    code = "otp_attempts_exceeded"
    default_message = "Too many incorrect code attempts"


class NoPendingAction(BssError):
    code = "no_pending_action"
    default_message = "No pending action to confirm"


class OfferNotEligible(BssError):
    code = "offer_not_eligible"
    default_message = "Not eligible for this offer"


class InsufficientPoints(BssError):
    code = "insufficient_points"
    default_message = "Not enough reward points"


class CaseNotFound(BssError):
    code = "case_not_found"
    default_message = "Support case not found"


class InvalidRequest(BssError):
    code = "invalid_request"
    default_message = "Invalid request"


class NotificationNotFound(BssError):
    code = "notification_not_found"
    default_message = "Notification not found"


class IncidentNotFound(BssError):
    code = "incident_not_found"
    default_message = "Network incident not found"
