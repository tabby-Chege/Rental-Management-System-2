from datetime import date, timedelta

from server.extensions import db
from server.models import Payment, Property
from server.models_unit_lease import Lease, Unit
from tests.test_tenants import client, world, seed_tenant


def make_lease(client, world, owner_key="landlord", tenant_key="tenant_user"):
    """Create a property, unit, tenant, and lease for payment tests."""
    tenant_email = f"{tenant_key}@example.com"

    tenant = seed_tenant(
        client,
        world["ids"][owner_key],
        name=f"Test {tenant_key}",
        email=tenant_email,
        user_id=world["ids"][tenant_key],
    )
    tenant_id = tenant["id"]

    owner_id = world["ids"][owner_key]

    prop = Property(
        owner_id=owner_id,
        name=f"Property {owner_key}",
        address="1 Test Street",
        city="Nairobi",
        state="Nairobi",
    )
    db.session.add(prop)
    db.session.flush()

    unit = Unit(
        unit_number=f"UNIT-{owner_key}",
        property_id=prop.id,
        bedrooms=1,
        bathrooms=1,
        rent_amount=1000,
    )
    db.session.add(unit)
    db.session.flush()

    lease = Lease(
        unit_id=unit.id,
        tenant_id=tenant_id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        monthly_rent=1000,
        deposit_amount=1000,
        is_active=True,
    )
    db.session.add(lease)
    db.session.commit()

    return lease.id


def add_payment(lease_id, reference_code):
    payment = Payment(
        lease_id=lease_id,
        amount=1000,
        payment_method="M-Pesa",
        status="Completed",
        reference_code=reference_code,
    )
    db.session.add(payment)
    db.session.commit()
    return payment.id


def test_payments_require_authentication(client):
    assert client.get("/payments").status_code == 401
    assert client.get("/api/payments").status_code == 401

    response = client.post(
        "/payments",
        json={
            "lease_id": 1,
            "amount": 1000,
            "payment_method": "M-Pesa",
        },
    )
    assert response.status_code == 401


def test_tenant_cannot_create_payment(client, world):
    response = client.post(
        "/payments",
        headers=world["tenant"],
        json={
            "lease_id": 1,
            "amount": 1000,
            "payment_method": "M-Pesa",
        },
    )
    assert response.status_code == 403


def test_landlord_can_record_payment_for_own_lease(client, world):
    lease_id = make_lease(client, world)

    response = client.post(
        "/payments",
        headers=world["landlord"],
        json={
            "lease_id": lease_id,
            "amount": 1000,
            "payment_method": "M-Pesa",
            "reference_code": "OWN-PAYMENT-001",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["lease_id"] == lease_id

def test_payment_defaults_to_pending_status(client, world):
    lease_id = make_lease(client, world)

    response = client.post(
        "/api/payments",
        headers=world["landlord"],
        json={
            "lease_id": lease_id,
            "amount": 1000,
            "payment_method": "M-Pesa",
            "reference_code": "PENDING-DEFAULT-001",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["status"] == "Pending"

def test_landlord_cannot_record_payment_for_another_landlord_lease(
    client, world
):
    lease_id = make_lease(
        client,
        world,
        owner_key="other",
        tenant_key="tenant_user2",
    )

    response = client.post(
        "/payments",
        headers=world["landlord"],
        json={
            "lease_id": lease_id,
            "amount": 1000,
            "payment_method": "M-Pesa",
            "reference_code": "UNAUTHORIZED-PAYMENT-001",
        },
    )

    assert response.status_code == 403


def test_landlord_sees_only_payments_for_own_properties(client, world):
    own_lease = make_lease(client, world)
    other_lease = make_lease(
        client,
        world,
        owner_key="other",
        tenant_key="tenant_user2",
    )

    own_payment_id = add_payment(own_lease, "LANDLORD-OWN-001")
    add_payment(other_lease, "LANDLORD-OTHER-001")

    response = client.get("/api/payments", headers=world["landlord"])

    assert response.status_code == 200
    payments = response.get_json()["payments"]
    payment_ids = {payment["id"] for payment in payments}
    assert own_payment_id in payment_ids
    assert len(payment_ids) == 1
    payment = payments[0]
    assert payment["tenant_name"] == "Test tenant_user"
    assert payment["property_name"] == "Property landlord"
    assert payment["unit_number"] == "UNIT-landlord"
    assert payment["payment_method"] == "M-Pesa"
    assert payment["reference_code"] == "LANDLORD-OWN-001"
    assert "password_hash" not in payment
    assert "access_token" not in payment


def test_tenant_sees_only_payments_for_own_leases(client, world):
    own_lease = make_lease(client, world)
    other_lease = make_lease(
        client,
        world,
        owner_key="other",
        tenant_key="tenant_user2",
    )

    own_payment_id = add_payment(own_lease, "TENANT-OWN-001")
    add_payment(other_lease, "TENANT-OTHER-001")

    response = client.get("/payments", headers=world["tenant"])

    assert response.status_code == 200
    payment_ids = {payment["id"] for payment in response.get_json()["payments"]}
    assert own_payment_id in payment_ids
    assert len(payment_ids) == 1
    assert response.get_json()["payments"][0]["tenant_name"] == "Test tenant_user"


def test_payment_history_returns_empty_for_users_without_payments(client, world):
    response = client.get("/api/payments", headers=world["tenant"])
    assert response.status_code == 200
    assert response.get_json()["payments"] == []
    assert response.get_json()["pagination"]["total"] == 0


def test_payment_validation_rejects_invalid_amount(client, world):
    lease_id = make_lease(client, world)

    response = client.post(
        "/payments",
        headers=world["landlord"],
        json={
            "lease_id": lease_id,
            "amount": -100,
            "payment_method": "M-Pesa",
        },
    )

    assert response.status_code == 400


def test_payment_uses_fixed_point_amount_and_currency_precision(client, world):
    lease_id = make_lease(client, world)
    lease = db.session.get(Lease, lease_id)
    unit = db.session.get(Unit, lease.unit_id)
    unit.property.currency = "KWD"
    db.session.commit()

    valid = client.post(
        "/api/payments",
        headers=world["landlord"],
        json={
            "lease_id": lease_id,
            "amount": 12.345,
            "payment_method": "Cash",
            "reference_code": "KWD-THREE-DECIMALS",
        },
    )
    assert valid.status_code == 201
    assert valid.get_json()["amount"] == 12.345
    assert valid.get_json()["currency"] == "KWD"

    too_precise = client.post(
        "/api/payments",
        headers=world["landlord"],
        json={
            "lease_id": lease_id,
            "amount": 12.3456,
            "payment_method": "Cash",
        },
    )
    assert too_precise.status_code == 400

    unit.property.currency = "JPY"
    db.session.commit()
    fractional_yen = client.post(
        "/api/payments",
        headers=world["landlord"],
        json={
            "lease_id": lease_id,
            "amount": 12.5,
            "payment_method": "Cash",
        },
    )
    assert fractional_yen.status_code == 400


def test_payment_list_is_paginated(client, world):
    lease_id = make_lease(client, world)
    add_payment(lease_id, "PAGE-001")
    add_payment(lease_id, "PAGE-002")

    response = client.get(
        "/payments?page=2&per_page=1", headers=world["landlord"]
    )
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["payments"]) == 1
    assert data["pagination"]["page"] == 2
    assert data["pagination"]["total"] == 2


def test_lease_records_cannot_be_managed_by_another_landlord(client, world):
    own_lease_id = make_lease(client, world)
    other_lease_id = make_lease(
        client,
        world,
        owner_key="other",
        tenant_key="tenant_user2",
    )

    own_lease = db.session.get(Lease, own_lease_id)
    other_lease = db.session.get(Lease, other_lease_id)
    cross_owner = client.post(
        "/api/leases",
        headers=world["landlord"],
        json={
            "unit_id": own_lease.unit_id,
            "tenant_id": other_lease.tenant_id,
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=30)).isoformat(),
            "monthly_rent": 1000,
            "deposit_amount": 0,
        },
    )
    assert cross_owner.status_code == 404

    assert client.delete(
        f"/api/leases/{other_lease_id}", headers=world["landlord"]
    ).status_code == 404
    assert client.delete(
        f"/api/leases/{own_lease_id}", headers=world["tenant"]
    ).status_code == 403
    assert client.delete(
        f"/api/leases/{own_lease_id}", headers=world["landlord"]
    ).status_code == 200


def test_lease_collection_and_update_routes(client, world):
    lease_id = make_lease(client, world)

    listed = client.get("/api/leases", headers=world["landlord"])
    assert listed.status_code == 200
    assert any(lease["id"] == lease_id for lease in listed.get_json()["leases"])
    assert client.get(
        f"/api/leases/{lease_id}", headers=world["landlord"]
    ).status_code == 200

    updated = client.put(
        f"/api/leases/{lease_id}",
        headers=world["landlord"],
        json={"status": "ended"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["status"] == "ended"
    assert updated.get_json()["deposit"] == 1000
