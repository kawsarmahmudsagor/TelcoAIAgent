from fastapi.testclient import TestClient

from app.main import app
from app.models.telco import Package


def test_catalog_is_public_and_active_only(db):
    r = TestClient(app).get("/api/catalog/packages")
    assert r.status_code == 200
    body = r.json()
    active = {p.code for p in db.query(Package).filter(Package.is_active.is_(True))}
    assert {p["code"] for p in body} == active
    assert set(body[0]) == {
        "code", "name", "kind", "data_mb", "minutes", "sms", "validity_days", "price", "tag"
    }
    assert isinstance(body[0]["price"], (int, float))


def test_catalog_kind_filter(db):
    c = TestClient(app)
    data = c.get("/api/catalog/packages?kind=data").json()
    assert data and all(p["kind"] == "data" for p in data)
    assert c.get("/api/catalog/packages?kind=nope").status_code == 422
