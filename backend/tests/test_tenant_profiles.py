from io import BytesIO

from PIL import Image

from server.extensions import db
from server.models_tenant import TenantDocument, TenantProfile
from tests.test_applications import apply, create_unit
from tests.test_tenants import client, world  # noqa: F401


def test_tenant_can_update_private_profile_details(client, world):
    response = client.put(
        "/api/tenant-profile/me",
        headers=world["tenant"],
        json={
            "full_name": "Tom Tenant",
            "phone": "+254722000000",
            "employment_status": "self_employed",
            "employer": "Tom's business",
            "job_title": "Owner",
            "emergency_contact_name": "Alex Contact",
            "emergency_contact_phone": "+254711111111",
            "emergency_contact_relationship": "Sibling",
            "id_type": "national_id",
            "id_number": "123456789",
            "previous_landlord_name": "Previous manager",
            "previous_landlord_contact": "previous@example.com",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["profile"]["id_number"] == "123456789"
    profile = TenantProfile.query.filter_by(
        user_id=world["ids"]["tenant_user"]
    ).one()
    assert profile.encrypted_id_number != "123456789"
    assert profile.full_name == "Tom Tenant"


def test_tenant_profile_validates_phone_and_access(client, world):
    invalid = client.put(
        "/api/tenant-profile/me",
        headers=world["tenant"],
        json={"phone": "0712345678"},
    )
    assert invalid.status_code == 400
    assert client.get("/api/tenant-profile/me", headers=world["landlord"]).status_code == 403


def test_application_keeps_profile_snapshot_after_profile_edit(client, world):
    unit_id = create_unit(client, world["landlord"])
    submitted = apply(client, world["tenant"], unit_id)
    assert submitted.status_code == 201
    application = submitted.get_json()["application"]

    updated = client.put(
        "/api/tenant-profile/me",
        headers=world["tenant"],
        json={"full_name": "Tom Updated"},
    )
    assert updated.status_code == 200

    listed = client.get("/api/applications", headers=world["landlord"])
    saved_application = listed.get_json()["applications"][0]
    assert saved_application["id"] == application["id"]
    assert saved_application["applicant_profile"]["full_name"] == "Tom"


def test_document_upload_is_private_and_application_scoped(
    client, world, monkeypatch
):
    stored = {}
    monkeypatch.setattr(
        "server.routes.tenant_profiles.put_private_object",
        lambda key, contents, content_type: stored.update(
            {key: (contents, content_type)}
        ),
    )
    monkeypatch.setattr(
        "server.routes.tenant_profiles.get_private_object",
        lambda key: stored[key][0],
    )
    monkeypatch.setattr(
        "server.routes.tenant_profiles.delete_private_object",
        lambda key: stored.pop(key, None),
    )

    image_bytes = BytesIO()
    Image.new("RGB", (8, 8), color="green").save(image_bytes, format="PNG")
    uploaded = client.post(
        "/api/tenant-profile/me/documents",
        headers=world["tenant"],
        data={
            "kind": "identity",
            "file": (BytesIO(image_bytes.getvalue()), "identity.png"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    document = uploaded.get_json()["document"]
    assert document["download_url"] == f"/api/tenant-documents/{document['id']}"
    assert len(stored) == 1

    denied = client.get(
        document["download_url"], headers=world["other"]
    )
    assert denied.status_code == 404

    unit_id = create_unit(client, world["landlord"])
    application = apply(client, world["tenant"], unit_id).get_json()["application"]
    assert application["applicant_profile"]["document_ids"] == [document["id"]]

    downloaded = client.get(
        document["download_url"], headers=world["landlord"]
    )
    assert downloaded.status_code == 200
    assert downloaded.data == stored[next(iter(stored))][0]
    assert downloaded.headers["Cache-Control"] == "private, no-store"

    removal = client.delete(
        f"/api/tenant-profile/me/documents/{document['id']}",
        headers=world["tenant"],
    )
    assert removal.status_code == 409
    assert db.session.get(TenantDocument, document["id"]) is not None


def test_document_upload_rejects_unsupported_files(client, world):
    response = client.post(
        "/api/tenant-profile/me/documents",
        headers=world["tenant"],
        data={
            "kind": "identity",
            "file": (BytesIO(b"<svg><script>alert(1)</script></svg>"), "id.svg"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_document_upload_uses_local_private_storage_when_configured(
    client, world, tmp_path
):
    client.application.config.update(
        OBJECT_STORAGE_BACKEND="local",
        LOCAL_STORAGE_PATH=str(tmp_path),
    )
    image_bytes = BytesIO()
    Image.new("RGB", (8, 8), color="green").save(image_bytes, format="PNG")
    response = client.post(
        "/api/tenant-profile/me/documents",
        headers=world["tenant"],
        data={
            "kind": "identity",
            "file": (BytesIO(image_bytes.getvalue()), "identity.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    document = response.get_json()["document"]
    stored_document = db.session.get(TenantDocument, document["id"])
    stored_object = tmp_path / stored_document.object_key
    assert stored_object.is_file()

    downloaded = client.get(
        document["download_url"],
        headers=world["tenant"],
    )
    assert downloaded.status_code == 200
    assert downloaded.data == stored_object.read_bytes()
