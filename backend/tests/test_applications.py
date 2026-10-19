from datetime import date, timedelta

from server.extensions import db
from server.models_tenant import Tenant
from server.models_unit_lease import Lease
from tests.test_tenants import client, world  # noqa: F401 (shared fixtures)


def create_unit(client, headers, name="Application property", rent_amount=1200):
    property_response = client.post(
        "/api/properties",
        headers=headers,
        json={
            "name": name,
            "address": "1 Main Street",
            "city": "Nairobi",
            "state": "Nairobi",
        },
    )
    assert property_response.status_code == 201
    property_id = property_response.get_json()["property"]["id"]
    unit_response = client.post(
        f"/api/properties/{property_id}/units",
        headers=headers,
        json={"unit_number": "A1", "rent_amount": rent_amount},
    )
    assert unit_response.status_code == 201
    return unit_response.get_json()["id"]


def apply(client, headers, unit_id, **values):
    body = {
        "unit_id": unit_id,
        "move_in_date": "2026-11-01",
        "message": "I would like to rent this unit.",
    }
    body.update(values)
    return client.post("/api/applications", headers=headers, json=body)


def test_application_requires_login(client):
    assert client.get("/api/applications").status_code == 401
    assert client.post("/api/applications", json={}).status_code == 401


def test_tenant_applies_and_sees_only_own_applications(client, world):
    unit_id = create_unit(client, world["landlord"])
    response = apply(client, world["tenant"], unit_id)
    assert response.status_code == 201
    application = response.get_json()["application"]
    assert application["status"] == "pending"
    assert application["applicant_user_id"] == world["ids"]["tenant_user"]
    assert application["tenant_id"] is None
    assert application["unit"]["id"] == unit_id
    assert application["property"]["name"] == "Application property"
    assert application["applicant"]["email"] == "tom@x.com"

    listed = client.get("/api/applications", headers=world["tenant"])
    assert listed.status_code == 200
    assert [item["id"] for item in listed.get_json()["applications"]] == [
        application["id"]
    ]
    assert client.get(
        f"/api/applications/{application['id']}", headers=world["tenant2"]
    ).status_code == 404


def test_landlord_application_list_is_scoped_to_owned_units(client, world):
    owned_unit = create_unit(client, world["landlord"], "Owned")
    other_unit = create_unit(client, world["other"], "Not owned")
    owned_app = apply(client, world["tenant"], owned_unit)
    other_app = apply(client, world["tenant2"], other_unit)
    assert owned_app.status_code == 201, owned_app.get_json()
    assert other_app.status_code == 201, other_app.get_json()

    listed = client.get("/api/applications", headers=world["landlord"])
    assert listed.status_code == 200
    assert [item["id"] for item in listed.get_json()["applications"]] == [
        owned_app.get_json()["application"]["id"]
    ]

    other_id = other_app.get_json()["application"]["id"]
    assert client.get(
        f"/api/applications/{other_id}", headers=world["landlord"]
    ).status_code == 404
    assert client.patch(
        f"/api/applications/{other_id}",
        headers=world["landlord"],
        json={"status": "approved"},
    ).status_code == 404


def test_application_validation_and_duplicate_pending_application(client, world):
    unit_id = create_unit(client, world["landlord"])
    assert apply(client, world["landlord"], unit_id).status_code == 403
    assert apply(client, world["tenant"], "1").status_code == 400
    assert apply(client, world["tenant"], 0).status_code == 400
    assert apply(client, world["tenant"], 99999).status_code == 404
    assert apply(
        client, world["tenant"], unit_id, move_in_date="not-a-date"
    ).status_code == 400
    assert apply(client, world["tenant"], unit_id, message=[]).status_code == 400

    assert apply(client, world["tenant"], unit_id).status_code == 201
    duplicate = apply(client, world["tenant"], unit_id)
    assert duplicate.status_code == 409


def test_tenant_cannot_apply_to_a_unit_with_an_active_lease(client, world):
    unit_id = create_unit(client, world["landlord"])
    tenant = Tenant(
        landlord_id=world["ids"]["landlord"],
        user_id=world["ids"]["tenant_user"],
        name="Tom",
        email="tom@x.com",
    )
    db.session.add(tenant)
    db.session.flush()
    db.session.add(
        Lease(
            unit_id=unit_id,
            tenant_id=tenant.id,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=30),
            monthly_rent=1200,
            deposit=0,
            status="active",
        )
    )
    db.session.commit()

    available = client.get("/api/units/public?availability=vacant")
    occupied = client.get("/api/units/public?availability=occupied")
    assert available.get_json()["pagination"]["total"] == 0
    assert occupied.get_json()["pagination"]["total"] == 1

    response = apply(client, world["tenant"], unit_id)
    assert response.status_code == 409
    assert "not available" in response.get_json()["error"]


def test_landlord_approval_creates_tenant_and_returns_lease_prefill(client, world):
    unit_id = create_unit(client, world["landlord"], rent_amount=1450)
    application = apply(client, world["tenant"], unit_id).get_json()["application"]

    approved = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    payload = approved.get_json()
    tenant = payload["tenant"]
    assert tenant["user_id"] == world["ids"]["tenant_user"]
    assert tenant["landlord_id"] == world["ids"]["landlord"]
    assert payload["application"]["tenant_id"] == tenant["id"]
    assert payload["lease_prefill"] == {
        "tenant_id": tenant["id"],
        "unit_id": unit_id,
        "start_date": "2026-11-01",
        "monthly_rent": 1450.0,
    }
    assert client.get("/api/tenants/me", headers=world["tenant"]).get_json()[
        "tenant"
    ]["id"] == tenant["id"]

    lease_prefill = payload["lease_prefill"]
    lease_prefill["end_date"] = "2027-10-31"
    lease_prefill["deposit"] = 500
    lease = client.post(
        "/api/leases",
        headers=world["landlord"],
        json=lease_prefill,
    )
    assert lease.status_code == 201
    assert lease.get_json()["tenant_id"] == tenant["id"]
    assert lease.get_json()["unit_id"] == unit_id

    repeated_decision = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved"},
    )
    assert repeated_decision.status_code == 409


def test_tenant_cannot_decide_application_and_decline_does_not_create_tenant(
    client, world
):
    unit_id = create_unit(client, world["landlord"])
    application = apply(client, world["tenant"], unit_id).get_json()["application"]
    endpoint = f"/api/applications/{application['id']}"

    assert client.patch(
        endpoint, headers=world["tenant"], json={"status": "approved"}
    ).status_code == 403
    declined = client.patch(
        endpoint, headers=world["landlord"], json={"status": "declined"}
    )
    assert declined.status_code == 200
    assert declined.get_json()["application"]["tenant_id"] is None
    assert client.get("/api/tenants/me", headers=world["tenant"]).status_code == 404
