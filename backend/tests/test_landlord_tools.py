from datetime import date, timedelta
from io import BytesIO

from PIL import Image

from server.extensions import db
from server.models import Payment, Property
from server.models_payment import RentInvoice
from server.models_unit_lease import Lease, Unit
from tests.test_payments import make_lease
from tests.test_tenants import client, world


def test_tenant_can_create_maintenance_request_and_landlord_updates_status(
    client, world
):
    lease_id = make_lease(client, world)
    created = client.post(
        "/api/maintenance",
        headers=world["tenant"],
        json={
            "lease_id": lease_id,
            "title": "Leaking kitchen tap",
            "description": "Water is leaking under the sink.",
        },
    )
    assert created.status_code == 201
    request_id = created.get_json()["request"]["id"]
    assert created.get_json()["request"]["status"] == "submitted"

    updated = client.patch(
        f"/api/maintenance/{request_id}",
        headers=world["landlord"],
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["request"]["status"] == "in_progress"
    assert client.get(
        "/api/maintenance", headers=world["other"]
    ).get_json()["requests"] == []


def test_maintenance_requests_are_private_and_need_active_tenant_lease(client, world):
    lease_id = make_lease(client, world)
    lease = db.session.get(Lease, lease_id)
    lease.status = "ended"
    db.session.commit()

    denied = client.post(
        "/api/maintenance",
        headers=world["tenant"],
        json={
            "lease_id": lease_id,
            "title": "Broken window",
            "description": "The window does not close.",
        },
    )
    assert denied.status_code == 404
    assert client.get("/api/maintenance").status_code == 401


def test_maintenance_photo_upload_and_download_are_private(client, world, monkeypatch):
    stored = {}
    monkeypatch.setattr(
        "server.routes.landlord_tools.put_private_object",
        lambda key, content, content_type: stored.update({key: content}),
    )
    monkeypatch.setattr(
        "server.routes.landlord_tools.get_private_object",
        lambda key: stored[key],
    )
    lease_id = make_lease(client, world)
    request_id = client.post(
        "/api/maintenance",
        headers=world["tenant"],
        json={
            "lease_id": lease_id,
            "title": "Damaged wall",
            "description": "Photo attached.",
        },
    ).get_json()["request"]["id"]
    content = BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(content, format="PNG")
    response = client.post(
        f"/api/maintenance/{request_id}/photos",
        headers=world["tenant"],
        data={"file": (BytesIO(content.getvalue()), "wall.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    photo = response.get_json()["photo"]
    assert client.get(photo["download_url"], headers=world["other"]).status_code == 404
    downloaded = client.get(photo["download_url"], headers=world["landlord"])
    assert downloaded.status_code == 200
    with Image.open(BytesIO(downloaded.data)) as image:
        assert image.format == "PNG"
        assert image.size == (10, 10)
    assert downloaded.headers["Cache-Control"] == "private, no-store"


def test_lease_documents_are_shared_only_with_lease_parties(client, world, monkeypatch):
    stored = {}
    monkeypatch.setattr(
        "server.routes.landlord_tools.put_private_object",
        lambda key, content, content_type: stored.update({key: content}),
    )
    monkeypatch.setattr(
        "server.routes.landlord_tools.get_private_object",
        lambda key: stored[key],
    )
    lease_id = make_lease(client, world)
    pdf = b"%PDF-1.4\nlease contents\n%%EOF"
    uploaded = client.post(
        f"/api/leases/{lease_id}/documents",
        headers=world["landlord"],
        data={"file": (BytesIO(pdf), "lease agreement.pdf")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    document = uploaded.get_json()["document"]
    assert document["filename"] == "lease_agreement.pdf"
    assert client.get(
        document["download_url"], headers=world["tenant2"]
    ).status_code == 404
    response = client.get(document["download_url"], headers=world["tenant"])
    assert response.status_code == 200
    assert response.data == pdf


def test_report_returns_income_arrears_and_occupancy_by_owned_property(
    client, world
):
    lease_id = make_lease(client, world)
    lease = db.session.get(Lease, lease_id)
    unit = db.session.get(Unit, lease.unit_id)
    prop = db.session.get(Property, unit.property_id)
    db.session.add(
        Payment(
            lease_id=lease.id,
            amount=1000,
            currency=prop.currency,
            payment_method="Bank Transfer",
            status="Completed",
            payment_type="rent",
        )
    )
    db.session.add(
        RentInvoice(
            lease_id=lease.id,
            due_date=date.today() - timedelta(days=2),
            amount=1000,
            amount_paid=200,
            currency=prop.currency,
            status="overdue",
        )
    )
    db.session.commit()

    result = client.get("/api/reports/portfolio", headers=world["landlord"])
    assert result.status_code == 200
    row = next(item for item in result.get_json()["properties"] if item["property_id"] == prop.id)
    assert row["rent_income"] == 1000
    assert row["rent_arrears"] == 800
    assert row["occupied_units"] == 1
    assert client.get("/api/reports/portfolio", headers=world["tenant"]).status_code == 403
