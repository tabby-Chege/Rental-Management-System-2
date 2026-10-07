from tests.test_tenants import client, world, create  # noqa: F401  (fixtures + helper)

from server.extensions import db


def test_landlord_deletes_own_tenant(client, world):
    tid = create(client, world["landlord"]).get_json()["tenant"]["id"]
    res = client.delete(f"/api/tenants/{tid}", headers=world["landlord"])
    assert res.status_code == 200
    assert client.get(f"/api/tenants/{tid}", headers=world["landlord"]).status_code == 404


def test_other_landlord_cannot_delete(client, world):
    tid = create(client, world["landlord"]).get_json()["tenant"]["id"]
    res = client.delete(f"/api/tenants/{tid}", headers=world["other"])
    assert res.status_code == 404
    assert client.get(f"/api/tenants/{tid}", headers=world["landlord"]).status_code == 200


def test_tenant_role_cannot_delete(client, world):
    tid = create(
        client, world["landlord"], user_id=world["ids"]["tenant_user"]
    ).get_json()["tenant"]["id"]
    res = client.delete(f"/api/tenants/{tid}", headers=world["tenant"])
    assert res.status_code == 403


def test_delete_requires_login(client):
    assert client.delete("/api/tenants/1").status_code == 401


def test_delete_blocked_when_tenant_has_leases(client, world):
    # Stand-in for David's Lease model, so the 409 path is exercised.
    if "Lease" not in db.Model.registry._class_registry:
        class Lease(db.Model):
            __tablename__ = "leases"
            id = db.Column(db.Integer, primary_key=True)
            tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)

        db.create_all()
    from server.routes.tenants import tenant_has_leases  # noqa: F401

    tid = create(client, world["landlord"]).get_json()["tenant"]["id"]
    lease_model = db.Model.registry._class_registry["Lease"]
    db.session.add(lease_model(tenant_id=tid))
    db.session.commit()

    res = client.delete(f"/api/tenants/{tid}", headers=world["landlord"])
    assert res.status_code == 409
    assert client.get(f"/api/tenants/{tid}", headers=world["landlord"]).status_code == 200
