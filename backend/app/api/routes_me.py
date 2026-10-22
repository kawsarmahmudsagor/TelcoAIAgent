"""Customer portal: the signed-in subscriber's own data."""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_subscriber, get_db
from app.api.schemas_me import PortalMe
from app.bss.accounts import mask_msisdn
from app.models.telco import Subscriber

router = APIRouter(prefix="/api/me", tags=["portal"])
_NO_STORE = {"Cache-Control": "no-store"}


def portal_me(sub: Subscriber) -> PortalMe:
    return PortalMe(
        subscriber_id=sub.id,
        full_name=sub.full_name,
        first_name=sub.full_name.split()[0],
        msisdn=sub.msisdn,
        masked_msisdn=mask_msisdn(sub.msisdn),
        plan_type=sub.plan_type,
        district=sub.district,
    )


@router.get("", response_model=PortalMe)
def me(
    response: Response,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber),
    db: Session = Depends(get_db),
) -> PortalMe:
    response.headers.update(_NO_STORE)
    return portal_me(db.get(Subscriber, subscriber_id))
