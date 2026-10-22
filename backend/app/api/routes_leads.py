import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.models.client import LeadStatus
from app.repositories import client_repo
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate

router = APIRouter(
    prefix="/api/leads", tags=["leads"], dependencies=[Depends(get_current_admin)]
)


@router.get("", response_model=list[ClientOut])
def list_leads(
    db: Session = Depends(get_db),
    lead_status: LeadStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    return client_repo.list_all(db, lead_status=lead_status, limit=limit, offset=offset)


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_lead(payload: ClientCreate, db: Session = Depends(get_db)):
    return client_repo.create(db, payload.model_dump())


@router.get("/{lead_id}", response_model=ClientOut)
def get_lead(lead_id: uuid.UUID, db: Session = Depends(get_db)):
    client = client_repo.get(db, lead_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return client


@router.patch("/{lead_id}", response_model=ClientOut)
def update_lead(lead_id: uuid.UUID, payload: ClientUpdate, db: Session = Depends(get_db)):
    client = client_repo.get(db, lead_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return client_repo.update(db, client, payload.model_dump(exclude_unset=True))
