import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.models.offer import Offer
from app.repositories import offer_repo
from app.schemas.offer import OfferCreate, OfferOut, OfferUpdate

router = APIRouter(prefix="/api/offers", tags=["offers"], dependencies=[Depends(get_current_admin)])


def _get_or_404(db: Session, offer_id: uuid.UUID) -> Offer:
    offer = offer_repo.get(db, offer_id)
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    return offer


@router.get("", response_model=list[OfferOut])
def list_offers(db: Session = Depends(get_db)) -> list:
    return offer_repo.list_all(db)


@router.get("/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_or_404(db, offer_id)


@router.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(payload: OfferCreate, db: Session = Depends(get_db)):
    try:
        return offer_repo.create(db, payload.model_dump())
    except offer_repo.OfferValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.patch("/{offer_id}", response_model=OfferOut)
def update_offer(offer_id: uuid.UUID, payload: OfferUpdate, db: Session = Depends(get_db)):
    offer = _get_or_404(db, offer_id)
    current = OfferOut.model_validate(offer).model_dump(
        include=set(OfferCreate.model_fields)
    )
    # Merge, then validate the result as a whole (a type change may need a percent, etc.).
    try:
        merged = OfferCreate.model_validate(
            {**current, **payload.model_dump(exclude_unset=True)}
        )
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            # loc/msg only: the raw input may hold dates and UUIDs, which aren't JSON.
            [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()],
        ) from exc
    try:
        return offer_repo.update(db, offer, merged.model_dump())
    except offer_repo.OfferValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(offer_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    offer_repo.delete(db, _get_or_404(db, offer_id))
