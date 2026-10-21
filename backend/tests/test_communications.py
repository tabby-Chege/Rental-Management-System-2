from tests.test_tenants import client, world  # noqa: F401
from tests.test_applications import create_unit


def test_tenant_can_ask_about_a_property_before_applying(client, world):
    unit_id = create_unit(client, world["landlord"])
    property_id = client.get(
        f"/api/units/{unit_id}", headers=world["landlord"]
    ).get_json()["unit"]["property_id"]

    response = client.post(
        "/api/conversations",
        headers=world["tenant"],
        json={"property_id": property_id, "body": "Is parking available?"},
    )
    assert response.status_code == 201
    payload = response.get_json()
    conversation = payload["conversation"]
    assert conversation["property"]["id"] == property_id
    assert conversation["other_party"]["role"] == "landlord"
    assert payload["message"]["body"] == "Is parking available?"

    landlord_threads = client.get(
        "/api/conversations", headers=world["landlord"]
    ).get_json()["conversations"]
    assert [item["id"] for item in landlord_threads] == [conversation["id"]]

    messages = client.get(
        f"/api/conversations/{conversation['id']}/messages",
        headers=world["landlord"],
    )
    assert messages.status_code == 200
    assert messages.get_json()["messages"][0]["sender_user_id"] == world["ids"]["tenant_user"]


def test_conversation_replies_are_private_to_the_tenant_and_property_owner(
    client, world
):
    unit_id = create_unit(client, world["landlord"])
    unit = client.get(f"/api/units/{unit_id}", headers=world["landlord"]).get_json()["unit"]
    created = client.post(
        "/api/conversations",
        headers=world["tenant"],
        json={"property_id": unit["property_id"], "body": "Can I view it?"},
    ).get_json()
    conversation_id = created["conversation"]["id"]

    reply = client.post(
        f"/api/conversations/{conversation_id}/messages",
        headers=world["landlord"],
        json={"body": "Yes, viewing is available this weekend."},
    )
    assert reply.status_code == 201
    assert reply.get_json()["message"]["sender_user_id"] == world["ids"]["landlord"]

    assert client.get(
        f"/api/conversations/{conversation_id}/messages",
        headers=world["tenant2"],
    ).status_code == 404
    assert client.get(
        f"/api/conversations/{conversation_id}/messages",
        headers=world["other"],
    ).status_code == 404


def test_conversation_input_and_roles_are_validated(client, world):
    assert client.post(
        "/api/conversations",
        headers=world["landlord"],
        json={"property_id": 1, "body": "Hello"},
    ).status_code == 403
    assert client.post(
        "/api/conversations",
        headers=world["tenant"],
        json={"property_id": 1, "body": "  "},
    ).status_code == 400
    assert client.post(
        "/api/conversations",
        headers=world["tenant"],
        json={"property_id": 99999, "body": "Hello"},
    ).status_code == 404
    assert client.get("/api/conversations").status_code == 401


def test_existing_property_conversation_is_reused(client, world):
    unit_id = create_unit(client, world["landlord"])
    unit = client.get(f"/api/units/{unit_id}", headers=world["landlord"]).get_json()["unit"]
    first = client.post(
        "/api/conversations",
        headers=world["tenant"],
        json={"property_id": unit["property_id"], "body": "Question one"},
    ).get_json()
    second = client.post(
        "/api/conversations",
        headers=world["tenant"],
        json={"property_id": unit["property_id"], "body": "Question two"},
    ).get_json()

    assert second["conversation"]["id"] == first["conversation"]["id"]
    messages = client.get(
        f"/api/conversations/{first['conversation']['id']}/messages",
        headers=world["tenant"],
    ).get_json()["messages"]
    assert [message["body"] for message in messages] == [
        "Question one",
        "Question two",
    ]


def test_property_with_message_history_cannot_be_deleted(client, world):
    property_response = client.post(
        "/api/properties",
        headers=world["landlord"],
        json={
            "name": "Question property",
            "address": "2 Main Street",
            "city": "Nairobi",
        },
    )
    property_id = property_response.get_json()["property"]["id"]
    started = client.post(
        "/api/conversations",
        headers=world["tenant"],
        json={"property_id": property_id, "body": "Is parking available?"},
    )
    assert started.status_code == 201

    deleted = client.delete(
        f"/api/properties/{property_id}", headers=world["landlord"]
    )
    assert deleted.status_code == 409
    assert "message history" in deleted.get_json()["error"]
