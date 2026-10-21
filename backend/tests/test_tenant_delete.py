from datetime import date

from tests.test_tenants import client, world, seed_tenant  # noqa: F401
from server.extensions import db
from server.models import Property
from server.models_unit_lease import Lease, Unit


def test_landlord_deletes_own_tenant(client, world):
    tid = seed_tenant(client, world["ids"]["landlord"])["id"]
    res = client.delete(f"/api/tenants/{tid}", headers=world["landlord"])
    assert res.status_code == 200
    assert client.get(f"/api/tenants/{tid}", headers=world["landlord"]).status_code == 404


def test_other_landlord_cannot_delete(client, world):
    tid = seed_tenant(client, world["ids"]["landlord"])["id"]
    res = client.delete(f"/api/tenants/{tid}", headers=world["other"])
    assert res.status_code == 404
    assert client.get(f"/api/tenants/{tid}", headers=world["landlord"]).status_code == 200


def test_tenant_role_cannot_delete(client, world):
    tid = seed_tenant(
        client,
        world["ids"]["landlord"],
        user_id=world["ids"]["tenant_user"],
    )["id"]
    res = client.delete(f"/api/tenants/{tid}", headers=world["tenant"])
    assert res.status_code == 403


def test_delete_requires_login(client):
    assert client.delete("/api/tenants/1").status_code == 401


def test_delete_blocked_when_tenant_has_leases(client, world):
    tid = seed_tenant(client, world["ids"]["landlord"])["id"]
    property_item = Property(
        owner_id=world["ids"]["landlord"],
        name="Test Property",
        address="1 Main Street",
        city="Nairobi",
        state="Nairobi",
    )
    db.session.add(property_item)
    db.session.flush()
    unit = Unit(unit_number="A1", property_id=property_item.id, rent_amount=1200)
    db.session.add(unit)
    db.session.flush()
    db.session.add(
        Lease(
            unit_id=unit.id,
            tenant_id=tid,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_rent=1200,
            deposit_amount=500,
        )
    )
    db.session.commit()

    res = client.delete(f"/api/tenants/{tid}", headers=world["landlord"])
    assert res.status_code == 409
    assert client.get(f"/api/tenants/{tid}", headers=world["landlord"]).status_code == 200
