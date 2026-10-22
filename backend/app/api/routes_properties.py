import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.repositories import property_repo
from app.schemas.property import PropertyCreate, PropertyOut, PropertyUpdate
from app.services import rag_service

router = APIRouter(
    prefix="/api/properties", tags=["properties"], dependencies=[Depends(get_current_admin)]
)


@router.get("", response_model=list[PropertyOut])
def list_properties(db: Session = Depends(get_db), limit: int = 100, offset: int = 0) -> list:
    return property_repo.list_all(db, limit=limit, offset=offset)


@router.post("", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
def create_property(payload: PropertyCreate, db: Session = Depends(get_db)):
    prop = property_repo.create(db, payload.model_dump())
    rag_service.enqueue_properties_sync_if_present(db)
    return prop


@router.patch("/{property_id}", response_model=PropertyOut)
def update_property(property_id: uuid.UUID, payload: PropertyUpdate, db: Session = Depends(get_db)):
    prop = property_repo.get(db, property_id)
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    prop = property_repo.update_fields(db, prop, payload.model_dump(exclude_unset=True))
    rag_service.enqueue_properties_sync_if_present(db)
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    # Soft delete: bookings and past conversations still reference the row.
    prop = property_repo.get(db, property_id)
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    property_repo.update_fields(db, prop, {"is_active": False})
    rag_service.enqueue_properties_sync_if_present(db)
