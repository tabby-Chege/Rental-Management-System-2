from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models_application import Application
from server.models_tenant import Tenant
from server.models_unit_lease import Lease
from tests.test_tenants import client, world  # noqa: F401 (shared fixtures)


def create_unit(
    client,
    headers,
    name="Application property",
    rent_amount=1200,
):
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
        "move_in_date": (date.today() + timedelta(days=30)).isoformat(),
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
    assert application["applicant_profile"]["full_name"] == "Tom"
    assert application["applicant_profile"]["employment_status"] == "employed"
    assert application["applicant_profile"]["document_ids"] == []

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


def test_payment_confirmation_creates_the_lease_after_reservation(client, world):
    unit_id = create_unit(client, world["landlord"], rent_amount=1450)
    application = apply(client, world["tenant"], unit_id).get_json()["application"]

    approved = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={
            "status": "approved",
            "reason": "The requested move-in date is available.",
        },
    )
    assert approved.status_code == 200
    payload = approved.get_json()
    tenant = payload["tenant"]
    assert tenant["user_id"] == world["ids"]["tenant_user"]
    assert tenant["landlord_id"] == world["ids"]["landlord"]
    assert payload["application"]["tenant_id"] == tenant["id"]
    assert payload["application"]["status"] == "approved"
    assert payload["application"]["payment_due_at"]
    listed_tenants = client.get(
        "/api/tenants", headers=world["landlord"]
    ).get_json()["tenants"]
    assert tenant["id"] in {record["id"] for record in listed_tenants}
    assert client.get("/api/tenants/me", headers=world["tenant"]).get_json()[
        "tenant"
    ]["id"] == tenant["id"]

    blocked_lease = client.post(
        "/api/leases",
        headers=world["landlord"],
        json={
            "tenant_id": tenant["id"],
            "unit_id": unit_id,
            "start_date": application["move_in_date"],
            "end_date": (
                date.fromisoformat(application["move_in_date"])
                + timedelta(days=365)
            ).isoformat(),
            "monthly_rent": 1450,
            "deposit": 500,
        },
    )
    assert blocked_lease.status_code == 409

    confirmation_body = {
        "lease_end_date": (
            date.fromisoformat(application["move_in_date"])
            + timedelta(days=365)
        ).isoformat(),
        "amount": 1450,
        "payment_method": "Bank Transfer",
        "reference_code": "BANK-REF-001",
    }
    confirmation = client.post(
        f"/api/applications/{application['id']}/confirm-payment",
        headers=world["landlord"],
        json=confirmation_body,
    )
    assert confirmation.status_code == 201
    confirmation_payload = confirmation.get_json()
    assert confirmation_payload["lease"]["tenant_id"] == tenant["id"]
    assert confirmation_payload["lease"]["unit_id"] == unit_id
    assert confirmation_payload["payment"]["status"] == "Completed"
    assert confirmation_payload["application"]["status"] == "paid"
    repeated_confirmation = client.post(
        f"/api/applications/{application['id']}/confirm-payment",
        headers=world["landlord"],
        json=confirmation_body,
    )
    assert repeated_confirmation.status_code == 200
    assert (
        repeated_confirmation.get_json()["lease"]["id"]
        == confirmation_payload["lease"]["id"]
    )


def test_approval_reservation_deadline_is_exactly_one_hour(client, world, monkeypatch):
    fixed_now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("server.routes.applications.utc_now", lambda: fixed_now)
    unit_id = create_unit(client, world["landlord"])
    application = apply(client, world["tenant"], unit_id).get_json()["application"]

    approval = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "The application is complete."},
    )

    assert approval.status_code == 200
    assert datetime.fromisoformat(
        approval.get_json()["application"]["payment_due_at"]
    ) == fixed_now + timedelta(hours=1)


def test_database_rejects_simultaneous_active_reservations_for_one_unit(
    client, world
):
    unit_id = create_unit(client, world["landlord"])
    first = Application(
        unit_id=unit_id,
        applicant_user_id=world["ids"]["tenant_user"],
        move_in_date=date.today() + timedelta(days=30),
        profile_snapshot={},
        status="pending",
    )
    second = Application(
        unit_id=unit_id,
        applicant_user_id=world["ids"]["tenant_user2"],
        move_in_date=date.today() + timedelta(days=30),
        profile_snapshot={},
        status="pending",
    )
    db.session.add_all([first, second])
    db.session.flush()

    first.status = "approved"
    db.session.flush()
    second.status = "offered"
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_tenant_cannot_decide_application_and_decline_does_not_create_tenant(
    client, world
):
    unit_id = create_unit(client, world["landlord"])
    application = apply(client, world["tenant"], unit_id).get_json()["application"]
    endpoint = f"/api/applications/{application['id']}"

    assert client.patch(
        endpoint, headers=world["tenant"], json={"status": "approved"}
    ).status_code == 403
    missing_reason = client.patch(
        endpoint,
        headers=world["landlord"],
        json={"status": "declined"},
    )
    assert missing_reason.status_code == 400
    declined = client.patch(
        endpoint,
        headers=world["landlord"],
        json={"status": "declined", "reason": "The move-in date is unavailable."},
    )
    assert declined.status_code == 200
    assert declined.get_json()["application"]["tenant_id"] is None
    assert (
        declined.get_json()["application"]["decision_reason"]
        == "The move-in date is unavailable."
    )
    assert client.get("/api/tenants/me", headers=world["tenant"]).status_code == 404


def test_waitlist_offer_deadline_notifications_and_expiry(
    client, world, monkeypatch
):
    unit_id = create_unit(client, world["landlord"])
    first = apply(client, world["tenant"], unit_id).get_json()["application"]
    second = apply(client, world["tenant2"], unit_id).get_json()["application"]
    assert second["status"] == "pending"

    approval = client.patch(
        f"/api/applications/{first['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "The application is complete."},
    )
    assert approval.status_code == 200

    queued = client.get("/api/applications", headers=world["tenant2"]).get_json()[
        "applications"
    ][0]
    assert queued["status"] == "waitlisted"

    fixed_now = datetime.now(timezone.utc) + timedelta(seconds=10)
    monkeypatch.setattr("server.reservations.utc_now", lambda: fixed_now)
    with client.application.app_context():
        application = db.session.get(Application, first["id"])
        application.payment_due_at = fixed_now - timedelta(minutes=1)
        db.session.commit()

    reserved_units = client.get(
        "/api/units/public?availability=reserved"
    ).get_json()["units"]
    assert [unit["id"] for unit in reserved_units] == [unit_id]

    offered = client.get("/api/applications", headers=world["tenant2"]).get_json()[
        "applications"
    ][0]
    assert offered["status"] == "offered"
    assert datetime.fromisoformat(offered["payment_due_at"]) == (
        fixed_now + timedelta(hours=1)
    )

    with client.application.app_context():
        application = db.session.get(Application, second["id"])
        application.payment_due_at = fixed_now + timedelta(minutes=10)
        db.session.commit()

    notifications = client.get(
        "/api/notifications", headers=world["tenant2"]
    ).get_json()["notifications"]
    notification_types = {item["notification_type"] for item in notifications}
    assert "waitlist_offer" in notification_types
    assert "reservation_reminder" in notification_types

    notification = notifications[0]
    read = client.patch(
        f"/api/notifications/{notification['id']}/read",
        headers=world["tenant2"],
    )
    assert read.status_code == 200
    assert read.get_json()["notification"]["read_at"]

    late_payment = client.post(
        f"/api/applications/{first['id']}/confirm-payment",
        headers=world["landlord"],
        json={
            "lease_end_date": "2027-10-31",
            "amount": 1200,
            "payment_method": "Bank Transfer",
        },
    )
    assert late_payment.status_code == 409


def test_reservation_deadline_cannot_be_extended(client, world):
    unit_id = create_unit(client, world["landlord"])
    application = apply(client, world["tenant"], unit_id).get_json()["application"]
    approval = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "The application is complete."},
    )
    rejected = client.post(
        f"/api/applications/{application['id']}/extend-deadline",
        headers=world["landlord"],
        json={"additional_hours": 24},
    )
    assert rejected.status_code == 404


def test_reservation_actions_are_restricted_to_the_property_owner(client, world):
    unit_id = create_unit(client, world["landlord"])
    application = apply(client, world["tenant"], unit_id).get_json()["application"]
    approval = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "The application is complete."},
    )
    assert approval.status_code == 200

    assert client.post(
        f"/api/applications/{application['id']}/extend-deadline",
        headers=world["tenant"],
        json={"additional_hours": 24},
    ).status_code == 404
    assert client.post(
        f"/api/applications/{application['id']}/confirm-payment",
        headers=world["tenant"],
        json={},
    ).status_code == 403
