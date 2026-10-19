from server import create_app
from datetime import timedelta

from flask_jwt_extended import create_access_token

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


def test_public_property_search_includes_other_owners_and_city_filters(client, world):
    owned = create_property(client, world["landlord"], "Nairobi home")
    other = create_property(client, world["other"], "Mombasa home", city="Mombasa")
    assert owned.status_code == other.status_code == 201

    response = client.get("/api/properties/public?city=Nairobi")
    assert response.status_code == 200
    properties = response.get_json()["properties"]
    assert [prop["name"] for prop in properties] == ["Nairobi home"]

    all_properties = client.get("/api/properties/public").get_json()["properties"]
    assert {prop["name"] for prop in all_properties} == {
        "Nairobi home",
        "Mombasa home",
    }


def test_public_property_units_and_filters(client, world):
    property_id = create_property(
        client, world["landlord"], "Public listing"
    ).get_json()["property"]["id"]
    created = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={"unit_number": "A1", "bedrooms": 2, "rent_amount": 1200},
    )
    assert created.status_code == 201

    result = client.get(
        f"/api/properties/public?bedrooms=2&min_rent=1000&max_rent=1500"
    )
    assert result.status_code == 200
    assert [prop["id"] for prop in result.get_json()["properties"]] == [property_id]

    units = client.get(f"/api/properties/public/{property_id}/units")
    assert units.status_code == 200
    assert units.get_json()["units"][0]["unit_number"] == "A1"
    assert units.get_json()["units"][0]["bedrooms"] == 2
    assert client.get("/api/properties/public?bedrooms=-1").status_code == 400


def test_unit_bedrooms_create_update_and_persist(client, world):
    property_id = create_property(
        client, world["landlord"], "Studio listing"
    ).get_json()["property"]["id"]
    created = client.post(
        "/api/units",
        headers=world["landlord"],
        json={
            "property_id": property_id,
            "unit_number": "S0",
            "bedrooms": 0,
        },
    )
    assert created.status_code == 201
    unit_id = created.get_json()["id"]
    assert created.get_json()["bedrooms"] == 0

    refreshed = client.get(
        f"/api/units/{unit_id}", headers=world["landlord"]
    )
    assert refreshed.status_code == 200
    assert refreshed.get_json()["unit"]["bedrooms"] == 0

    public_unit = client.get(
        f"/api/properties/public/{property_id}/units"
    ).get_json()["units"][0]
    assert public_unit["bedrooms"] == 0
    assert client.get(
        f"/api/properties/public/{property_id}/units?unit_id={unit_id}"
    ).get_json()["units"][0]["id"] == unit_id
    assert client.get(
        f"/api/properties/public/{property_id}/units?unit_id=not-an-id"
    ).status_code == 400

    updated = client.put(
        f"/api/units/{unit_id}",
        headers=world["landlord"],
        json={"bedrooms": 2},
    )
    assert updated.status_code == 200
    assert updated.get_json()["bedrooms"] == 2
    assert client.get(
        f"/api/units/{unit_id}", headers=world["landlord"]
    ).get_json()["unit"]["bedrooms"] == 2

    for invalid_bedrooms in (-1, 1.5, True):
        response = client.put(
            f"/api/units/{unit_id}",
            headers=world["landlord"],
            json={"bedrooms": invalid_bedrooms},
        )
        assert response.status_code == 400


def test_unit_type_description_and_rent_persist_with_owner_authorization(client, world):
    property_id = create_property(
        client, world["landlord"], "Unit fields listing"
    ).get_json()["property"]["id"]
    created = client.post(
        "/api/units",
        headers=world["landlord"],
        json={
            "property_id": property_id,
            "unit_number": "B2",
            "unit_type": "two-bedroom",
            "bedrooms": 2,
            "bathrooms": 1.5,
            "rent_amount": 18500.75,
            "description": "Bright unit near the courtyard",
        },
    )
    assert created.status_code == 201
    unit_id = created.get_json()["id"]
    assert {
        key: created.get_json()[key]
        for key in ("unit_type", "bedrooms", "bathrooms", "rent_amount", "description")
    } == {
        "unit_type": "two-bedroom",
        "bedrooms": 2,
        "bathrooms": 1.5,
        "rent_amount": 18500.75,
        "description": "Bright unit near the courtyard",
    }

    updated = client.put(
        f"/api/units/{unit_id}",
        headers=world["landlord"],
        json={"unit_type": "studio", "bedrooms": 0, "bathrooms": 1, "rent_amount": 9000},
    )
    assert updated.status_code == 200
    assert updated.get_json()["unit_type"] == "studio"
    assert updated.get_json()["bedrooms"] == 0
    assert updated.get_json()["rent_amount"] == 9000
    assert client.get(
        f"/api/units/{unit_id}", headers=world["landlord"]
    ).get_json()["unit"]["bathrooms"] == 1

    assert client.put(
        f"/api/units/{unit_id}",
        headers=world["tenant"],
        json={"rent_amount": 1},
    ).status_code == 403
    assert client.delete(
        f"/api/units/{unit_id}", headers=world["tenant"]
    ).status_code == 403

    for field, value in (
        ("unit_type", "x" * 51),
        ("description", "x" * 5001),
        ("bathrooms", -0.5),
        ("bathrooms", 1.25),
        ("rent_amount", 0),
        ("rent_amount", float("inf")),
        ("rent_amount", 1.001),
    ):
        invalid = client.put(
            f"/api/units/{unit_id}",
            headers=world["landlord"],
            json={field: value},
        )
        assert invalid.status_code == 400, (field, value)


def test_public_unit_search_filters_real_units_and_excludes_occupied_by_default(
    client, world
):
    property_id = create_property(
        client, world["landlord"], "Riverside Apartments", city="Nairobi"
    ).get_json()["property"]["id"]
    created_units = []
    for unit_number, unit_type, bedrooms, bathrooms, rent in (
        ("A1", "one-bedroom", 1, 1, 12000),
        ("B2", "two-bedroom", 2, 1.5, 18500),
        ("S0", "studio", 0, 1, 8000),
    ):
        response = client.post(
            f"/api/properties/{property_id}/units",
            headers=world["landlord"],
            json={
                "unit_number": unit_number,
                "unit_type": unit_type,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "rent_amount": rent,
            },
        )
        assert response.status_code == 201
        created_units.append(response.get_json()["id"])

    matching = client.get(
        "/api/units/public?location=Riverside&bedrooms=2&bathrooms=1.5"
        "&min_rent=18000&max_rent=19000&unit_type=two-bedroom"
    )
    assert matching.status_code == 200
    result = matching.get_json()
    assert result["pagination"]["total"] == 1
    unit = result["units"][0]
    assert unit["id"] == created_units[1]
    assert unit["property_name"] == "Riverside Apartments"
    assert unit["unit_number"] == "B2"
    assert unit["bedrooms"] == 2
    assert unit["bathrooms"] == 1.5
    assert unit["rent_amount"] == 18500
    assert unit["availability_status"] == "vacant"

    assert client.get(
        "/api/units/public?location=Wrong+City"
    ).get_json()["pagination"]["total"] == 0
    assert client.get(
        "/api/units/public?min_rent=20000&max_rent=10000"
    ).status_code == 400
    assert client.get("/api/units/public?bedrooms=-1").status_code == 400


def test_public_property_cards_include_available_bedroom_layouts(client, world):
    property_id = create_property(
        client, world["landlord"], "Layout listing"
    ).get_json()["property"]["id"]
    for unit_number, bedrooms in (("S0", 0), ("A1", 1), ("A2", 1), ("B2", 2)):
        created = client.post(
            f"/api/properties/{property_id}/units",
            headers=world["landlord"],
            json={"unit_number": unit_number, "bedrooms": bedrooms},
        )
        assert created.status_code == 201

    public_property = client.get("/api/properties/public").get_json()["properties"][0]
    assert public_property["available_bedroom_counts"] == [0, 1, 2]


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


def test_expired_token_returns_session_message_without_creating_property(client, world):
    token = create_access_token(
        identity=str(world["ids"]["landlord"]),
        expires_delta=timedelta(seconds=-1),
    )
    response = client.post(
        "/api/properties",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Should not be created",
            "address": "1 Street",
            "city": "Nairobi",
            "state": "Nairobi",
        },
    )
    assert response.status_code == 401
    message = "Your session has ended. Please sign in again to continue."
    assert response.get_json()["error"] == message
    assert response.get_json()["msg"] == message
    assert response.get_json()["error"] != "Token has expired"
    assert client.get("/api/properties", headers=world["landlord"]).get_json()[
        "pagination"
    ]["total"] == 0


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


def test_units_collection_routes_support_the_units_page(client, world):
    property_id = create_property(
        client, world["landlord"], "Units page home"
    ).get_json()["property"]["id"]
    created = client.post(
        "/api/units",
        headers=world["landlord"],
        json={"property_id": property_id, "unit_number": "B2"},
    )
    assert created.status_code == 201
    unit_id = created.get_json()["id"]
    assert client.get("/api/units", headers=world["landlord"]).get_json()["units"][0]["id"] == unit_id
    assert client.get(
        f"/api/units/{unit_id}", headers=world["landlord"]
    ).get_json()["unit_number"] == "B2"


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
