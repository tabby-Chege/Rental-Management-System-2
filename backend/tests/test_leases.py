from tests.test_payments import make_lease
from tests.test_tenants import client, world


def test_unit_collection_crud_matches_frontend_api(client, world):
    property_response = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Unit API property",
            "address": "1 Main Street",
            "city": "Nairobi",
            "state": "Nairobi",
        },
    )
    property_id = property_response.get_json()["property"]["id"]

    created = client.post(
        "/api/units",
        headers=world["landlord"],
        json={
            "property_id": property_id,
            "unit_number": "A1",
            "bedrooms": 2,
            "bathrooms": 1,
            "rent_amount": 1200,
        },
    )
    assert created.status_code == 201
    unit_id = created.get_json()["unit"]["id"]

    listing = client.get("/api/units", headers=world["landlord"])
    assert listing.status_code == 200
    assert listing.get_json()["units"][0]["id"] == unit_id
    assert client.get(f"/api/units/{unit_id}", headers=world["landlord"]).status_code == 200

    updated = client.put(
        f"/api/units/{unit_id}",
        headers=world["landlord"],
        json={"rent_amount": 1300},
    )
    assert updated.status_code == 200
    assert updated.get_json()["unit"]["rent_amount"] == 1300
    assert client.delete(
        f"/api/units/{unit_id}", headers=world["landlord"]
    ).status_code == 200


def test_lease_read_update_and_termination_are_owner_scoped(client, world):
    lease_id = make_lease(client, world)
    endpoint = f"/api/leases/{lease_id}"

    listing = client.get("/api/leases", headers=world["landlord"])
    assert listing.status_code == 200
    assert listing.get_json()["leases"][0]["id"] == lease_id

    details = client.get(endpoint, headers=world["landlord"])
    assert details.status_code == 200
    assert details.get_json()["lease"]["id"] == lease_id

    assert client.get(endpoint, headers=world["other"]).status_code == 404
    assert client.put(
        endpoint, headers=world["other"], json={"monthly_rent": 1100}
    ).status_code == 404

    updated = client.put(
        endpoint,
        headers=world["landlord"],
        json={"monthly_rent": 1100, "deposit": 500, "status": "ended"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["lease"]["monthly_rent"] == 1100
    assert updated.get_json()["lease"]["deposit"] == 500
    assert updated.get_json()["lease"]["status"] == "ended"

    assert client.delete(endpoint, headers=world["landlord"]).status_code == 200
    assert client.get(endpoint, headers=world["landlord"]).get_json()["lease"]["status"] == "terminated"
