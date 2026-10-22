from server import create_app
from datetime import date, timedelta

from flask_jwt_extended import create_access_token

from server.extensions import db
from server.models_media import PropertyPhoto
from server.models_tenant import Tenant
from server.models_unit_lease import Lease
from tests.test_tenants import client, world  # noqa: F401


def test_health_endpoint():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret-key-for-tests-only-0123456789",
        "REQUIRE_TWO_FACTOR": False,
        "TENANT_PII_ENCRYPTION_KEY": (
            "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        ),
    })
    app.config["TESTING"] = True

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["message"] == "Rental Management API is running"


def test_properties_require_authentication():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret-key-for-tests-only-0123456789",
        "REQUIRE_TWO_FACTOR": False,
        "TENANT_PII_ENCRYPTION_KEY": (
            "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        ),
    })
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


def test_reservation_hold_cannot_be_configured_on_properties(client, world):
    response = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Fixed deadline property",
            "address": "1 Main Street",
            "city": "Nairobi",
            "reservation_hold_hours": 48,
        },
    )
    assert response.status_code == 400
    assert "fixed one-hour" in response.get_json()["error"]

    created = create_property(client, world["landlord"], "Fixed deadline property")
    assert created.status_code == 201
    property_data = created.get_json()["property"]
    assert "reservation_hold_hours" not in property_data
    update = client.put(
        f"/api/properties/{property_data['id']}",
        headers=world["landlord"],
        json={"reservation_hold_hours": 2},
    )
    assert update.status_code == 400


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


def test_public_unit_search_includes_cover_photo_url(client, world):
    property_id = create_property(
        client, world["landlord"], "Photo listing"
    ).get_json()["property"]["id"]
    created_unit = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={"unit_number": "A1", "bedrooms": 1},
    )
    assert created_unit.status_code == 201
    unit_id = created_unit.get_json()["id"]
    db.session.add(
        PropertyPhoto(
            property_id=property_id,
            object_key="property-cover-test",
            content_type="image/jpeg",
            file_size=1200,
            is_cover=True,
        )
    )
    db.session.add(
        PropertyPhoto(
            unit_id=unit_id,
            object_key="unit-cover-test",
            content_type="image/jpeg",
            file_size=1800,
            is_cover=True,
        )
    )
    db.session.commit()

    response = client.get("/api/units/public")

    assert response.status_code == 200
    unit = next(item for item in response.get_json()["units"] if item["id"] == unit_id)
    unit_photo = PropertyPhoto.query.filter_by(unit_id=unit_id).one()
    assert unit["photo_url"] == f"/api/public/photos/{unit_photo.id}"


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
            "password": "StrongRental!2026",
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


def test_property_supports_international_address_currency_and_time_zone(client, world):
    created = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "West Coast home",
            "address_line": "10 Market Street",
            "city": "San Francisco",
            "country": "US",
            "region": "California",
            "postal_code": "94105",
            "time_zone": "America/Los_Angeles",
            "currency": "USD",
        },
    )
    assert created.status_code == 201
    prop = created.get_json()["property"]
    assert {
        key: prop[key]
        for key in (
            "address_line", "country", "region", "city", "postal_code",
            "time_zone", "currency",
        )
    } == {
        "address_line": "10 Market Street",
        "country": "US",
        "region": "California",
        "city": "San Francisco",
        "postal_code": "94105",
        "time_zone": "America/Los_Angeles",
        "currency": "USD",
    }

    updated = client.put(
        f"/api/properties/{prop['id']}",
        headers=world["landlord"],
        json={"name": "Updated west coast home"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["property"]["currency"] == "USD"
    assert updated.get_json()["property"]["country"] == "US"

    for field, value in (
        ("currency", "US"),
        ("currency", "XYZ"),
        ("country", "USA"),
        ("time_zone", "No/Such_Zone"),
    ):
        invalid = client.post(
            "/api/properties",
            headers=world["landlord"],
            json={
                "name": "Invalid property",
                "address_line": "1 Main Street",
                "city": "Anywhere",
                field: value,
            },
        )
        assert invalid.status_code == 400


def test_unit_rent_uses_property_currency_precision(client, world):
    prop = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Kuwait home",
            "address_line": "1 Main Street",
            "city": "Kuwait City",
            "country": "KW",
            "time_zone": "Asia/Kuwait",
            "currency": "KWD",
        },
    ).get_json()["property"]
    created = client.post(
        f"/api/properties/{prop['id']}/units",
        headers=world["landlord"],
        json={"unit_number": "A1", "rent_amount": 123.456},
    )
    assert created.status_code == 201
    assert created.get_json()["currency"] == "KWD"
    assert created.get_json()["rent_amount"] == 123.456

    incompatible_currency = client.put(
        f"/api/properties/{prop['id']}",
        headers=world["landlord"],
        json={"currency": "USD"},
    )
    assert incompatible_currency.status_code == 409

    tenant = Tenant(
        landlord_id=world["ids"]["landlord"],
        name="Kuwait tenant",
        email="kw-tenant@example.com",
    )
    db.session.add(tenant)
    db.session.commit()
    today = date.today()
    lease = client.post(
        "/api/leases",
        headers=world["landlord"],
        json={
            "unit_id": created.get_json()["id"],
            "tenant_id": tenant.id,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=90)).isoformat(),
            "monthly_rent": 123.456,
            "deposit": 10.001,
        },
    )
    assert lease.status_code == 201
    assert lease.get_json()["currency"] == "KWD"
    assert lease.get_json()["monthly_rent"] == 123.456
    assert lease.get_json()["deposit"] == 10.001
    assert client.put(
        f"/api/properties/{prop['id']}",
        headers=world["landlord"],
        json={"currency": "USD"},
    ).status_code == 409

    invalid = client.post(
        f"/api/properties/{prop['id']}/units",
        headers=world["landlord"],
        json={"unit_number": "A2", "rent_amount": 123.4567},
    )
    assert invalid.status_code == 400


def test_whole_property_creates_exactly_one_non_deletable_unit(client, world):
    created = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Garden bungalow",
            "address_line": "4 Garden Lane",
            "city": "Nairobi",
            "country": "KE",
            "time_zone": "Africa/Nairobi",
            "currency": "KES",
            "rental_type": "whole_property",
            "subtype": "bungalow",
            "floors": 1,
            "whole_unit": {
                "bedrooms": 3,
                "bathrooms": 2,
                "rent_amount": 25000,
                "layout": "3+1",
                "size": 140,
                "size_unit": "sqm",
                "furnished": True,
            },
        },
    )
    assert created.status_code == 201
    prop = created.get_json()["property"]
    assert prop["rental_type"] == "whole_property"
    assert prop["subtype"] == "bungalow"
    assert prop["floors"] == 1

    unit_response = client.get(
        f"/api/properties/public/{prop['id']}/units"
    )
    assert unit_response.status_code == 200
    units = unit_response.get_json()["units"]
    assert len(units) == 1
    unit = units[0]
    assert unit["unit_number"] == "Entire property"
    assert unit["bedrooms"] == 3
    assert unit["layout"] == "3+1"
    assert unit["size"] == 140
    assert unit["furnished"] is True

    extra = client.post(
        f"/api/properties/{prop['id']}/units",
        headers=world["landlord"],
        json={"unit_number": "A2"},
    )
    assert extra.status_code == 409
    renamed = client.put(
        f"/api/units/{unit['id']}",
        headers=world["landlord"],
        json={"unit_number": "Garden bungalow"},
    )
    assert renamed.status_code == 409
    assert client.delete(
        f"/api/units/{unit['id']}", headers=world["landlord"]
    ).status_code == 409


def test_multi_unit_floor_layout_and_room_validation(client, world):
    property_response = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Four floor block",
            "address_line": "12 Example Road",
            "city": "Nairobi",
            "country": "KE",
            "time_zone": "Africa/Nairobi",
            "currency": "KES",
            "rental_type": "multi_unit",
            "subtype": "apartment_block",
            "floors": 4,
        },
    )
    assert property_response.status_code == 201
    property_id = property_response.get_json()["property"]["id"]
    created = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={
            "unit_number": "201",
            "floor_number": 2,
            "layout": "2+1",
            "bathrooms": 1.5,
            "rent_amount": 18000,
            "size": 75.5,
            "size_unit": "sqm",
            "furnished": False,
        },
    )
    assert created.status_code == 201
    unit = created.get_json()
    assert unit["bedrooms"] == 2
    assert unit["floor_number"] == 2
    assert unit["size_unit"] == "sqm"

    too_high = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={"unit_number": "501", "floor_number": 5},
    )
    assert too_high.status_code == 400
    mismatch = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={"unit_number": "202", "layout": "2+1", "bedrooms": 1},
    )
    assert mismatch.status_code == 400

    room_response = client.post(
        f"/api/units/{unit['id']}/rooms",
        headers=world["landlord"],
        json={
            "name": "Main bedroom",
            "room_type": "bedroom",
            "size": 14.25,
            "size_unit": "sqm",
            "description": "Bedroom with courtyard view",
        },
    )
    assert room_response.status_code == 201
    room = room_response.get_json()["room"]
    assert room["name"] == "Main bedroom"
    assert client.get(
        f"/api/units/{unit['id']}", headers=world["landlord"]
    ).get_json()["unit"]["rooms"] == [room]
    resized_room = client.put(
        f"/api/rooms/{room['id']}",
        headers=world["landlord"],
        json={"size": 15.5},
    )
    assert resized_room.status_code == 200
    assert resized_room.get_json()["room"]["size_unit"] == "sqm"
    assert client.get(
        f"/api/units/{unit['id']}/rooms", headers=world["other"]
    ).status_code == 404
    updated_room = client.put(
        f"/api/rooms/{room['id']}",
        headers=world["landlord"],
        json={"description": "Updated description"},
    )
    assert updated_room.status_code == 200
    assert updated_room.get_json()["room"]["description"] == "Updated description"
    assert client.delete(
        f"/api/rooms/{room['id']}", headers=world["landlord"]
    ).status_code == 200


def test_property_floor_and_rental_type_cannot_break_existing_units(client, world):
    property_id = create_property(
        client, world["landlord"], "One floor home"
    ).get_json()["property"]["id"]
    unit = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={"unit_number": "2", "floor_number": 1},
    )
    assert unit.status_code == 201
    assert client.put(
        f"/api/properties/{property_id}",
        headers=world["landlord"],
        json={"rental_type": "whole_property"},
    ).status_code == 409
    assert client.put(
        f"/api/properties/{property_id}",
        headers=world["landlord"],
        json={"floors": 0},
    ).status_code == 400


def test_bulk_unit_creation_previews_floor_numbering_and_is_atomic(client, world):
    prop = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Bulk block",
            "address_line": "1 Main Road",
            "city": "Nairobi",
            "country": "KE",
            "time_zone": "Africa/Nairobi",
            "currency": "KES",
            "floors": 4,
        },
    ).get_json()["property"]
    endpoint = f"/api/properties/{prop['id']}/units/bulk"
    created = client.post(
        endpoint,
        headers=world["landlord"],
        json={"units_per_floor": 5, "layout": "2+1", "rent_amount": 18000},
    )
    assert created.status_code == 201
    payload = created.get_json()
    assert payload["created_count"] == 20
    assert [unit["unit_number"] for unit in payload["units"][:5]] == [
        "101", "102", "103", "104", "105",
    ]
    assert [unit["unit_number"] for unit in payload["units"][5:10]] == [
        "201", "202", "203", "204", "205",
    ]
    assert all(unit["layout"] == "2+1" and unit["bedrooms"] == 2 for unit in payload["units"])

    collision = client.post(
        endpoint,
        headers=world["landlord"],
        json={"units_per_floor": 5, "layout": "2+1", "rent_amount": 18000},
    )
    assert collision.status_code == 409
    assert client.get(
        f"/api/properties/{prop['id']}/units",
        headers=world["landlord"],
        query_string={"per_page": 100},
    ).get_json()["pagination"]["total"] == 20

    for invalid in (
        {"units_per_floor": 0, "layout": "2+1", "rent_amount": 18000},
        {"units_per_floor": 1, "layout": "invalid", "rent_amount": 18000},
        {"units_per_floor": 1, "layout": "2+1", "rent_amount": 18000.123},
        {"units_per_floor": 1, "layout": "2+1"},
    ):
        assert client.post(endpoint, headers=world["landlord"], json=invalid).status_code == 400


def test_property_occupancy_counts_reserved_and_occupied_units(client, world):
    property_id = create_property(
        client, world["landlord"], "Occupancy summary"
    ).get_json()["property"]["id"]
    unit_ids = []
    for unit_number in ("A1", "A2", "A3"):
        response = client.post(
            f"/api/properties/{property_id}/units",
            headers=world["landlord"],
            json={"unit_number": unit_number, "rent_amount": 15000},
        )
        assert response.status_code == 201
        unit_ids.append(response.get_json()["id"])

    initial = client.get(
        f"/api/properties/{property_id}", headers=world["landlord"]
    ).get_json()["property"]["occupancy_summary"]
    assert initial == {
        "total_units": 3,
        "occupied_units": 0,
        "reserved_units": 0,
        "vacant_units": 3,
    }

    application = client.post(
        "/api/applications",
        headers=world["tenant"],
        json={
            "unit_id": unit_ids[0],
            "move_in_date": "2026-11-01",
            "message": "",
        },
    ).get_json()["application"]
    approved = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "The applicant meets the listing criteria."},
    )
    assert approved.status_code == 200
    assert approved.get_json()["application"]["unit"]["availability_status"] == "reserved"

    tenant = Tenant(
        landlord_id=world["ids"]["landlord"],
        name="Occupancy tenant",
        email="occupancy-tenant@example.com",
    )
    db.session.add(tenant)
    db.session.flush()
    db.session.add(
        Lease(
            unit_id=unit_ids[1],
            tenant_id=tenant.id,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=30),
            monthly_rent=15000,
            deposit=0,
            status="active",
        )
    )
    db.session.commit()

    summary = client.get(
        f"/api/properties/public/{property_id}"
    ).get_json()["property"]["occupancy_summary"]
    assert summary == {
        "total_units": 3,
        "occupied_units": 1,
        "reserved_units": 1,
        "vacant_units": 1,
    }
    reserved_units = client.get(
        "/api/units/public?availability=reserved"
    ).get_json()["units"]
    assert [unit["id"] for unit in reserved_units] == [unit_ids[0]]
    assert client.get(
        "/api/units/public?availability=vacant"
    ).get_json()["pagination"]["total"] == 1


def test_approved_application_reserves_unit_and_waitlists_other_applicants(client, world):
    property_id = create_property(
        client, world["landlord"], "Reserved unit"
    ).get_json()["property"]["id"]
    unit_id = client.post(
        f"/api/properties/{property_id}/units",
        headers=world["landlord"],
        json={"unit_number": "A1", "rent_amount": 15000},
    ).get_json()["id"]
    application = client.post(
        "/api/applications",
        headers=world["tenant"],
        json={"unit_id": unit_id, "move_in_date": "2026-11-01"},
    ).get_json()["application"]
    assert client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "Approved."},
    ).status_code == 200
    waitlisted = client.post(
        "/api/applications",
        headers=world["tenant2"],
        json={"unit_id": unit_id, "move_in_date": "2026-11-01"},
    )
    assert waitlisted.status_code == 201
    assert waitlisted.get_json()["application"]["status"] == "waitlisted"
    assert client.get(
        "/api/units/public?availability=vacant"
    ).get_json()["pagination"]["total"] == 0
