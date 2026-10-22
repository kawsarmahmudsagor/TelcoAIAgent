from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.services.excel_import_service import import_clients

router = APIRouter(prefix="/api/import", tags=["import"], dependencies=[Depends(get_current_admin)])


@router.post("/clients")
async def import_clients_route(file: UploadFile, db: Session = Depends(get_db)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expected an .xlsx file")
    content = await file.read()
    return import_clients(db, content)
