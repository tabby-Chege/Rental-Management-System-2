from server import create_app
from server.extensions import db
from tests.test_tenants import client, world  # noqa: F401


def test_health_endpoint():
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["message"] == "Rental Management API is running"


def test_properties_require_authentication():
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.get("/api/properties")

    assert response.status_code == 401


def create_property(client, headers, name, city="Nairobi"):
    return client.post(
        "/api/properties",
        headers=headers,
        json={
            "name": name,
            "address": f"{name} Street",
            "city": city,
            "state": "Nairobi",
        },
    )


def test_property_crud_and_owner_enforcement(client, world):
    created = create_property(client, world["landlord"], "Home")
    assert created.status_code == 201
    prop = created.get_json()["property"]
    assert prop["id"]
    assert prop["owner_id"] == world["ids"]["landlord"]

    prop_url = f"/api/properties/{prop['id']}"
    assert client.get(prop_url, headers=world["landlord"]).status_code == 200

    updated = client.put(
        prop_url, headers=world["landlord"], json={"name": "Updated home"}
    )
    assert updated.status_code == 200
    assert updated.get_json()["property"]["name"] == "Updated home"

    assert client.get(prop_url, headers=world["other"]).status_code == 404
    assert client.put(
        prop_url, headers=world["other"], json={"name": "Not mine"}
    ).status_code == 404
    assert client.delete(prop_url, headers=world["other"]).status_code == 404

    assert client.delete(prop_url, headers=world["landlord"]).status_code == 200
    assert client.get(prop_url, headers=world["landlord"]).status_code == 404


def test_property_pagination_and_search_are_user_scoped(client, world):
    for name in ("Oak Home", "Pine Home", "Lake Home"):
        assert create_property(client, world["landlord"], name).status_code == 201
    assert create_property(client, world["other"], "Other Home").status_code == 201

    first_page = client.get(
        "/api/properties?page=1&per_page=2&q=Home",
        headers=world["landlord"],
    )
    assert first_page.status_code == 200
    data = first_page.get_json()
    assert len(data["properties"]) == 2
    assert data["pagination"] == {
        "page": 1,
        "per_page": 2,
        "total": 3,
        "pages": 2,
        "has_next": True,
        "has_prev": False,
    }

    second_page = client.get(
        "/api/properties?page=2&per_page=2&q=Home",
        headers=world["landlord"],
    ).get_json()
    assert len(second_page["properties"]) == 1
    assert {item["name"] for item in data["properties"] + second_page["properties"]} == {
        "Oak Home",
        "Pine Home",
        "Lake Home",
    }


def test_property_pagination_rejects_invalid_parameters(client, world):
    response = client.get("/api/properties?page=0", headers=world["landlord"])
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_registration_creates_non_admin_landlord(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "New landlord",
            "email": "New@Example.com",
            "password": "password123",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.get_json()["user"]["role"] == "landlord"
    assert response.get_json()["user"]["email"] == "new@example.com"


def test_units_are_owned_crud_resources(client, world):
    property_response = create_property(client, world["landlord"], "Unit home")
    property_id = property_response.get_json()["property"]["id"]
    endpoint = f"/api/properties/{property_id}/units"

    created = client.post(
        endpoint,
        headers=world["landlord"],
        json={"unit_number": "A1", "rent_amount": 1200},
    )
    assert created.status_code == 201
    unit_id = created.get_json()["id"]
    unit_endpoint = f"/api/units/{unit_id}"

    units_list = client.get(endpoint, headers=world["landlord"])
    assert units_list.status_code == 200
    assert units_list.get_json()["units"][0]["id"] == unit_id
    assert units_list.get_json()["pagination"]["total"] == 1
    assert client.get(endpoint, headers=world["other"]).status_code == 404
    assert client.put(
        unit_endpoint, headers=world["other"], json={"unit_number": "B1"}
    ).status_code == 404
    assert client.delete(unit_endpoint, headers=world["other"]).status_code == 404

    updated = client.put(
        unit_endpoint,
        headers=world["landlord"],
        json={"rent_amount": 1300},
    )
    assert updated.status_code == 200
    assert updated.get_json()["rent_amount"] == 1300
    assert client.delete(unit_endpoint, headers=world["landlord"]).status_code == 200


def test_property_delete_preserves_linked_units(client, world):
    property_id = create_property(
        client, world["landlord"], "Occupied property"
    ).get_json()["property"]["id"]
    unit_response = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={"unit_number": "A1", "rent_amount": 1000},
    )
    assert unit_response.status_code == 201

    response = client.delete(
        f"/api/properties/{property_id}", headers=world["landlord"]
    )
    assert response.status_code == 409
    assert "units" in response.get_json()["error"]
