from tests.test_tenants import client, create, world  # noqa: F401

from server.extensions import db
from server.models import Property


def create_property(owner_id):
    property_item = Property(
        owner_id=owner_id,
        name="Test Property",
        address="1 Main Street",
        city="Nairobi",
        state="Nairobi",
    )
    db.session.add(property_item)
    db.session.commit()
    return property_item.id


def test_unit_and_lease_routes_share_app_models(client, world):
    property_id = create_property(world["ids"]["landlord"])
    unit_response = client.post(
        f"/properties/{property_id}/units",
        json={"unit_number": "A1", "rent_amount": 1200},
        headers=world["landlord"],
    )
    assert unit_response.status_code == 201
    unit = unit_response.get_json()

    tenant_id = create(
        client, world["landlord"], email="lease-tenant@example.com"
    ).get_json()["tenant"]["id"]
    lease_response = client.post(
        "/api/leases",
        json={
            "unit_id": unit["id"],
            "tenant_id": tenant_id,
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "monthly_rent": 1200,
            "deposit": 500,
        },
        headers=world["landlord"],
    )

    assert lease_response.status_code == 201
    assert lease_response.get_json()["deposit"] == 500.0
    assert lease_response.get_json()["status"] == "active"
    assert len(client.get("/api/leases", headers=world["landlord"]).get_json()) == 1


def test_units_are_scoped_to_property_owner(client, world):
    property_id = create_property(world["ids"]["landlord"])

    response = client.get(
        f"/properties/{property_id}/units", headers=world["other"]
    )

    assert response.status_code == 404
