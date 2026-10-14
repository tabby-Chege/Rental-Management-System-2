import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-tests-only-0123456789"

import pytest

from server import create_app
from server.extensions import db
from server.models import User


@pytest.fixture
def client():
    app = create_app()
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


def create(client, headers, **body):
    body.setdefault("name", "Tess Tenant")
    body.setdefault("email", "tess@x.com")
    return client.post("/api/tenants", json=body, headers=headers)


def test_requires_login(client):
    assert client.get("/api/tenants").status_code == 401


def test_landlord_creates_and_lists(client, world):
    res = create(client, world["landlord"], phone="0700")
    assert res.status_code == 201
    assert res.get_json()["tenant"]["landlord_id"] == world["ids"]["landlord"]
    listing = client.get("/api/tenants", headers=world["landlord"]).get_json()
    assert len(listing["tenants"]) == 1
    assert listing["pagination"]["total"] == 1


def test_tenant_list_pagination_is_scoped_to_landlord(client, world):
    for index in range(3):
        response = create(
            client,
            world["landlord"],
            name=f"Tenant {index}",
            email=f"tenant{index}@x.com",
        )
        assert response.status_code == 201

    create(client, world["other"], name="Other tenant", email="other@x.com")

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
    assert create(client, world["tenant"]).status_code == 403


def test_validation_and_bad_json(client, world):
    assert create(client, world["landlord"], name="").status_code == 400
    assert create(client, world["landlord"], email="nope").status_code == 400
    res = client.post("/api/tenants", data="not json", headers=world["landlord"])
    assert res.status_code == 400
    assert create(client, world["landlord"], user_id=9999).status_code == 400


def test_duplicate_email_case_insensitive(client, world):
    assert create(client, world["landlord"]).status_code == 201
    assert create(client, world["landlord"], email="TESS@x.com").status_code == 409
    # a different landlord may use the same email
    assert create(client, world["other"]).status_code == 201


def test_landlords_cannot_see_each_others_tenants(client, world):
    tid = create(client, world["landlord"]).get_json()["tenant"]["id"]
    assert client.get("/api/tenants/%d" % tid, headers=world["other"]).status_code == 404
    assert client.put("/api/tenants/%d" % tid, json={"name": "Hax"}, headers=world["other"]).status_code == 404
    assert client.get("/api/tenants", headers=world["other"]).get_json()["tenants"] == []


def test_tenant_sees_only_own_record(client, world):
    uid = world["ids"]["tenant_user"]
    mine = create(client, world["landlord"], user_id=uid).get_json()["tenant"]["id"]
    theirs = create(client, world["landlord"], email="b@x.com").get_json()["tenant"]["id"]
    assert client.get("/api/tenants/me", headers=world["tenant"]).get_json()["tenant"]["id"] == mine
    assert client.get("/api/tenants/%d" % mine, headers=world["tenant"]).status_code == 200
    assert client.get("/api/tenants/%d" % theirs, headers=world["tenant"]).status_code == 404
    assert client.get("/api/tenants/me", headers=world["tenant2"]).status_code == 404


def test_tenant_can_edit_only_contact_fields(client, world):
    uid = world["ids"]["tenant_user"]
    tid = create(client, world["landlord"], user_id=uid).get_json()["tenant"]["id"]
    ok = client.put("/api/tenants/%d" % tid, json={"phone": "0711"}, headers=world["tenant"])
    assert ok.status_code == 200 and ok.get_json()["tenant"]["phone"] == "0711"
    for field in ("name", "user_id"):
        res = client.put("/api/tenants/%d" % tid, json={field: "x"}, headers=world["tenant"])
        assert res.status_code == 403


def test_landlord_can_edit_all_and_link_rules(client, world):
    tid = create(client, world["landlord"]).get_json()["tenant"]["id"]
    uid = world["ids"]["tenant_user"]
    res = client.put("/api/tenants/%d" % tid, json={"name": "New", "user_id": uid}, headers=world["landlord"])
    assert res.status_code == 200 and res.get_json()["tenant"]["user_id"] == uid
    other = create(client, world["landlord"], email="c@x.com").get_json()["tenant"]["id"]
    clash = client.put("/api/tenants/%d" % other, json={"user_id": uid}, headers=world["landlord"])
    assert clash.status_code == 409
    not_tenant = client.put("/api/tenants/%d" % other, json={"user_id": world["ids"]["other"]}, headers=world["landlord"])
    assert not_tenant.status_code == 400
