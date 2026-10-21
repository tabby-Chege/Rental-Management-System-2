from io import BytesIO

from PIL import Image

from server.extensions import db
from server.models_media import ListingReport, PropertyPhoto
from server.models_unit_lease import Room, Unit
from tests.test_applications import create_unit
from tests.test_tenants import client, world  # noqa: F401


def png_image(color="red"):
    output = BytesIO()
    Image.new("RGB", (12, 8), color=color).save(output, format="PNG")
    return output.getvalue()


def upload(client, url, content=None, filename="listing.png", data=None, headers=None):
    return client.post(
        url,
        headers=headers,
        data={
            **(data or {}),
            "file": (BytesIO(content or png_image()), filename),
        },
        content_type="multipart/form-data",
    )


def test_property_photo_upload_is_normalized_served_and_cover_can_change(
    client, world, monkeypatch
):
    unit_id = create_unit(client, world["landlord"])
    unit = db.session.get(Unit, unit_id)
    stored = {}
    monkeypatch.setattr(
        "server.routes.media.put_private_object",
        lambda key, contents, content_type: stored.update(
            {key: (contents, content_type)}
        ),
    )
    monkeypatch.setattr(
        "server.routes.media.get_private_object",
        lambda key: stored[key][0],
    )

    first = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        headers=world["landlord"],
    )
    assert first.status_code == 201
    first_photo = first.get_json()["photo"]
    assert first_photo["is_cover"] is True
    assert first_photo["content_type"] == "image/png"
    assert len(stored) == 1

    second = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        filename="second.png",
        headers=world["landlord"],
        data={"is_cover": "true"},
    )
    assert second.status_code == 201
    assert PropertyPhoto.query.filter_by(id=first_photo["id"]).one().is_cover is False
    second_photo = second.get_json()["photo"]
    assert second_photo["is_cover"] is True

    public_property = client.get(f"/api/properties/public/{unit.property_id}")
    assert public_property.status_code == 200
    assert public_property.get_json()["property"]["photos"][0]["is_cover"] is True
    served = client.get(second_photo["url"])
    assert served.status_code == 200
    assert served.mimetype == "image/png"
    assert served.headers["X-Content-Type-Options"] == "nosniff"


def test_property_photo_upload_works_with_local_object_storage(
    client, world, tmp_path
):
    client.application.config.update(
        OBJECT_STORAGE_BACKEND="local",
        LOCAL_STORAGE_PATH=str(tmp_path),
    )
    unit_id = create_unit(client, world["landlord"])
    unit = db.session.get(Unit, unit_id)

    uploaded = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        headers=world["landlord"],
    )

    assert uploaded.status_code == 201
    photo = uploaded.get_json()["photo"]
    stored_photo = db.session.get(PropertyPhoto, photo["id"])
    stored_object = tmp_path / stored_photo.object_key
    assert stored_object.is_file()

    served = client.get(photo["url"])
    assert served.status_code == 200
    assert served.mimetype == "image/png"
    assert served.data == stored_object.read_bytes()


def test_photo_upload_rejects_disallowed_extensions_and_fake_images(client, world):
    unit_id = create_unit(client, world["landlord"])
    unit = db.session.get(Unit, unit_id)
    svg = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        filename="photo.svg",
        headers=world["landlord"],
    )
    assert svg.status_code == 400
    fake = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        content=b"not an image",
        filename="photo.png",
        headers=world["landlord"],
    )
    assert fake.status_code == 400
    assert PropertyPhoto.query.count() == 0


def test_unit_photo_can_be_tagged_to_a_room_and_reports_are_validated(
    client, world, monkeypatch
):
    unit_id = create_unit(client, world["landlord"])
    unit = db.session.get(Unit, unit_id)
    room = Room(unit_id=unit.id, name="Kitchen", room_type="kitchen")
    db.session.add(room)
    db.session.commit()
    monkeypatch.setattr(
        "server.routes.media.put_private_object",
        lambda key, contents, content_type: None,
    )

    photo = upload(
        client,
        f"/api/units/{unit.id}/photos",
        headers=world["landlord"],
        data={"room_id": str(room.id)},
    )
    assert photo.status_code == 201
    assert photo.get_json()["photo"]["room_id"] == room.id

    report = client.post(
        "/api/listing-reports",
        headers=world["tenant"],
        json={
            "unit_id": unit.id,
            "reason": "inaccurate",
            "details": "The listing has incorrect details.",
        },
    )
    assert report.status_code == 201
    assert report.get_json()["report"]["status"] == "pending"
    assert ListingReport.query.count() == 1

    invalid = client.post(
        "/api/listing-reports",
        headers=world["tenant"],
        json={"unit_id": unit.id, "reason": [], "details": ""},
    )
    assert invalid.status_code == 400


def test_cover_management_preserves_one_cover_and_enforces_ownership(
    client, world, monkeypatch
):
    unit_id = create_unit(client, world["landlord"])
    unit = db.session.get(Unit, unit_id)
    monkeypatch.setattr(
        "server.routes.media.put_private_object",
        lambda key, contents, content_type: None,
    )
    monkeypatch.setattr(
        "server.routes.media.delete_private_object",
        lambda key: None,
    )
    first = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        headers=world["landlord"],
    ).get_json()["photo"]
    second = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        headers=world["landlord"],
        filename="second.png",
    ).get_json()["photo"]

    forbidden = client.patch(
        f"/api/photos/{first['id']}/cover", headers=world["other"]
    )
    assert forbidden.status_code == 404
    selected = client.patch(
        f"/api/photos/{second['id']}/cover", headers=world["landlord"]
    )
    assert selected.status_code == 200
    assert PropertyPhoto.query.filter_by(is_cover=True).one().id == second["id"]

    deleted = client.delete(
        f"/api/photos/{second['id']}", headers=world["landlord"]
    )
    assert deleted.status_code == 200
    assert PropertyPhoto.query.filter_by(is_cover=True).one().id == first["id"]


def test_tenants_cannot_upload_listing_photos(client, world):
    unit_id = create_unit(client, world["landlord"])
    unit = db.session.get(Unit, unit_id)
    response = upload(
        client,
        f"/api/properties/{unit.property_id}/photos",
        headers=world["tenant"],
    )
    assert response.status_code == 403
