"""Public pack catalog for the signed-out home page. Catalog data only, nothing per subscriber."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes_me import _json
from app.bss import packages
from app.bss.types import PackageView
from app.models.telco import PackageKind

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/packages", response_model=list[PackageView])
def list_packages(kind: PackageKind | None = None, db: Session = Depends(get_db)):
    return _json(packages.search(db, kind=kind))
