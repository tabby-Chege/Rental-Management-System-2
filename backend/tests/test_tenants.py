import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-tests-only-0123456789"
os.environ["TENANT_PII_ENCRYPTION_KEY"] = (
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
)

import pytest

from server import create_app
from server.extensions import db
from server.models import User
from server.models_tenant import Tenant, TenantProfile


@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret-key-for-tests-only-0123456789",
        "REQUIRE_TWO_FACTOR": False,
        "TENANT_PII_ENCRYPTION_KEY": (
            "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        ),
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app.test_client()
        db.session.remove()


def make_user(name, email, role):
    user = User(name=name, email=email, role=role)
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    if role == "tenant":
        db.session.add(
            TenantProfile(
                user_id=user.id,
                full_name=name,
                phone="+254700000000",
                employment_status="employed",
                employer="Example employer",
                job_title="Staff member",
                emergency_contact_name="Alex Contact",
                emergency_contact_phone="+254711111111",
                emergency_contact_relationship="Sibling",
            )
        )
        db.session.commit()
    return user.id


def login(client, email):
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": "Bearer " + res.get_json()["access_token"]}


@pytest.fixture
def world(client):
    ids = {
        "landlord": make_user("Lana", "lana@x.com", "landlord"),
        "other": make_user("Omar", "omar@x.com", "landlord"),
        "tenant_user": make_user("Tom", "tom@x.com", "tenant"),
        "tenant_user2": make_user("Tia", "tia@x.com", "tenant"),
    }
    return {
        "ids": ids,
        "landlord": login(client, "lana@x.com"),
        "other": login(client, "omar@x.com"),
        "tenant": login(client, "tom@x.com"),
        "tenant2": login(client, "tia@x.com"),
    }


def seed_tenant(client, landlord_id, **body):
    body.setdefault("name", "Tess Tenant")
    body.setdefault("email", "tess@x.com")
    with client.application.app_context():
        tenant = Tenant(
            landlord_id=landlord_id,
            user_id=body.get("user_id"),
            name=body["name"],
            email=body["email"],
            phone=body.get("phone"),
        )
        db.session.add(tenant)
        db.session.commit()
        return tenant.to_dict()


def test_requires_login(client):
    assert client.get("/api/tenants").status_code == 401


def test_landlord_lists_tenants(client, world):
    tenant = seed_tenant(
        client, world["ids"]["landlord"], phone="+254700000000"
    )
    listing = client.get("/api/tenants", headers=world["landlord"]).get_json()
    assert len(listing["tenants"]) == 1
    assert listing["tenants"][0]["id"] == tenant["id"]
    assert listing["pagination"]["total"] == 1


def test_landlords_cannot_manually_create_tenant_records(client, world):
    response = client.post(
        "/api/tenants",
        headers=world["landlord"],
        json={"name": "Tess", "email": "tess@example.com"},
    )
    assert response.status_code == 405


def test_tenant_list_pagination_is_scoped_to_landlord(client, world):
    for index in range(3):
        seed_tenant(
            client,
            world["ids"]["landlord"],
            name=f"Tenant {index}",
            email=f"tenant{index}@x.com",
        )

    seed_tenant(
        client, world["ids"]["other"], name="Other tenant", email="other@x.com"
    )

    first = client.get(
        "/api/tenants?page=1&per_page=2", headers=world["landlord"]
    )
    assert first.status_code == 200
    assert len(first.get_json()["tenants"]) == 2
    assert first.get_json()["pagination"]["total"] == 3
    assert first.get_json()["pagination"]["has_next"] is True

    second = client.get(
        "/api/tenants?page=2&per_page=2", headers=world["landlord"]
    )
    assert second.status_code == 200
    assert len(second.get_json()["tenants"]) == 1


def test_tenant_list_rejects_invalid_pagination(client, world):
    response = client.get("/api/tenants?per_page=0", headers=world["landlord"])
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_tenant_cannot_list_or_create(client, world):
    assert client.get("/api/tenants", headers=world["tenant"]).status_code == 403
    assert client.post(
        "/api/tenants", headers=world["tenant"], json={}
    ).status_code == 405


def test_linked_tenant_can_update_own_details_only(client, world):
    seed_tenant(
        client,
        world["ids"]["landlord"],
        name="Tom",
        email="tom@x.com",
        phone="+254700000000",
        user_id=world["ids"]["tenant_user"],
    )

    updated = client.put(
        "/api/tenants/me",
        headers=world["tenant"],
        json={"email": "tom.updated@x.com", "phone": "+254711000000"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["tenant"]["email"] == "tom.updated@x.com"
    assert updated.get_json()["tenant"]["phone"] == "+254711000000"
    assert client.put(
        "/api/tenants/me",
        headers=world["tenant"],
        json={"landlord_id": world["ids"]["other"]},
    ).status_code == 403
    assert client.put(
        "/api/tenants/me",
        headers=world["landlord"],
        json={"phone": "+254712000000"},
    ).status_code == 403


def test_validation_and_bad_json(client, world):
    res = client.post("/api/tenants", data="not json", headers=world["landlord"])
    assert res.status_code == 405


def test_landlord_cannot_change_tenant_email_to_a_duplicate(client, world):
    first = seed_tenant(client, world["ids"]["landlord"], email="first@x.com")
    second = seed_tenant(client, world["ids"]["landlord"], email="second@x.com")
    response = client.put(
        f"/api/tenants/{second['id']}",
        headers=world["landlord"],
        json={"email": first["email"]},
    )
    assert response.status_code == 409


def test_landlords_cannot_see_each_others_tenants(client, world):
    tid = seed_tenant(client, world["ids"]["landlord"])["id"]
    assert client.get("/api/tenants/%d" % tid, headers=world["other"]).status_code == 404
    assert client.put("/api/tenants/%d" % tid, json={"name": "Hax"}, headers=world["other"]).status_code == 404
    assert client.get("/api/tenants", headers=world["other"]).get_json()["tenants"] == []


def test_tenant_sees_only_own_record(client, world):
    uid = world["ids"]["tenant_user"]
    mine = seed_tenant(client, world["ids"]["landlord"], user_id=uid)["id"]
    theirs = seed_tenant(
        client, world["ids"]["landlord"], email="b@x.com"
    )["id"]
    assert client.get("/api/tenants/me", headers=world["tenant"]).get_json()["tenant"]["id"] == mine
    assert client.get("/api/tenants/%d" % mine, headers=world["tenant"]).status_code == 200
    assert client.get("/api/tenants/%d" % theirs, headers=world["tenant"]).status_code == 404
    assert client.get("/api/tenants/me", headers=world["tenant2"]).status_code == 404


def test_tenant_details_include_only_own_current_property_and_lease(client, world):
    tenant = seed_tenant(
        client,
        world["ids"]["landlord"],
        name="Tom",
        email="tom@x.com",
        user_id=world["ids"]["tenant_user"],
    )
    property_record = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Tenant home",
            "address": "12 Garden Road",
            "city": "Nairobi",
            "state": "Nairobi",
            "description": "A sunny apartment near the park.",
        },
    ).get_json()["property"]
    unit = client.post(
        f"/api/properties/{property_record['id']}/units",
        headers=world["landlord"],
        json={"unit_number": "B4", "bedrooms": 2, "bathrooms": 1, "rent_amount": 1500},
    ).get_json()
    today = date.today()
    lease_response = client.post(
        "/api/leases",
        headers=world["landlord"],
        json={
            "unit_id": unit["id"],
            "tenant_id": tenant["id"],
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=180)).isoformat(),
            "monthly_rent": 1500,
            "deposit": 3000,
        },
    )
    assert lease_response.status_code == 201

    details = client.get("/api/tenants/me", headers=world["tenant"])
    assert details.status_code == 200
    residence = details.get_json()["current_residences"][0]
    assert residence["property"]["id"] == property_record["id"]
    assert residence["property"]["address"] == "12 Garden Road"
    assert residence["property"]["description"] == "A sunny apartment near the park."
    assert residence["unit"]["unit_number"] == "B4"
    assert residence["lease"]["monthly_rent"] == 1500

    assert client.get("/api/tenants/me", headers=world["tenant2"]).status_code == 404


def test_tenant_can_edit_only_contact_fields(client, world):
    uid = world["ids"]["tenant_user"]
    tid = seed_tenant(client, world["ids"]["landlord"], user_id=uid)["id"]
    ok = client.put("/api/tenants/%d" % tid, json={"phone": "+254711000000"}, headers=world["tenant"])
    assert ok.status_code == 200 and ok.get_json()["tenant"]["phone"] == "+254711000000"
    for field in ("name", "user_id"):
        res = client.put("/api/tenants/%d" % tid, json={field: "x"}, headers=world["tenant"])
        assert res.status_code == 403


def test_landlord_can_edit_all_and_link_rules(client, world):
    tid = seed_tenant(client, world["ids"]["landlord"])["id"]
    uid = world["ids"]["tenant_user"]
    res = client.put(
        "/api/tenants/%d" % tid,
        json={"name": "New"},
        headers=world["landlord"],
    )
    assert res.status_code == 200 and res.get_json()["tenant"]["name"] == "New"
    forbidden_link = client.put(
        "/api/tenants/%d" % tid,
        json={"user_id": uid},
        headers=world["landlord"],
    )
    assert forbidden_link.status_code == 403
