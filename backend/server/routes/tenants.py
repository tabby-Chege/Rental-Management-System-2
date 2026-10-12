from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from server.extensions import db
from server.models import User
from server.models_tenant import Tenant

tenants_bp = Blueprint("tenants", __name__, url_prefix="/api/tenants")

MANAGER_ROLES = {"landlord", "admin"}
# Fields a tenant may change on their own record.
TENANT_EDITABLE = {"email", "phone"}
MANAGER_EDITABLE = {"name", "email", "phone", "user_id"}


def error(message, status):
    return {"error": message}, status


def current_user():
    verify_jwt_in_request()
    return db.session.get(User, int(get_jwt_identity()))


def clean_email(value):
    email = (value or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return None
    return email


def validate_user_link(user_id, tenant=None):
    """Return an error response if user_id cannot be linked, else None."""
    if user_id is None:
        return None
    linked = db.session.get(User, user_id) if isinstance(user_id, int) else None
    if not linked or linked.role != "tenant":
        return error("user_id must belong to an existing user with the tenant role", 400)
    taken = Tenant.query.filter_by(user_id=user_id).first()
    if taken and (tenant is None or taken.id != tenant.id):
        return error("That user account is already linked to a tenant", 409)
    return None


def get_visible_tenant(user, tenant_id):
    """Managers see only their own tenants; tenants see only themselves."""
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        return None
    if user.role in MANAGER_ROLES and tenant.landlord_id == user.id:
        return tenant
    if user.role == "tenant" and tenant.user_id == user.id:
        return tenant
    return None


@tenants_bp.route("", methods=["GET"])
def list_tenants():
    user = current_user()
    if not user:
        return error("User not found", 404)
    if user.role not in MANAGER_ROLES:
        return error("You do not have permission to access this resource", 403)

    tenants = Tenant.query.filter_by(landlord_id=user.id).order_by(Tenant.name).all()
    return {"tenants": [t.to_dict() for t in tenants]}, 200


@tenants_bp.route("", methods=["POST"])
def create_tenant():
    user = current_user()
    if not user:
        return error("User not found", 404)
    if user.role not in MANAGER_ROLES:
        return error("You do not have permission to access this resource", 403)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Request body must be valid JSON", 400)

    name = (data.get("name") or "").strip()
    email = clean_email(data.get("email"))
    phone = (data.get("phone") or "").strip() or None
    user_id = data.get("user_id")

    if not name:
        return error("Name is required", 400)
    if not email:
        return error("A valid email address is required", 400)
    if Tenant.query.filter_by(landlord_id=user.id, email=email).first():
        return error("You already have a tenant with this email", 409)

    problem = validate_user_link(user_id)
    if problem:
        return problem

    tenant = Tenant(
        landlord_id=user.id, user_id=user_id, name=name, email=email, phone=phone
    )
    db.session.add(tenant)
    db.session.commit()
    return {"message": "Tenant created", "tenant": tenant.to_dict()}, 201


@tenants_bp.route("/me", methods=["GET"])
def my_tenant_record():
    user = current_user()
    if not user:
        return error("User not found", 404)
    if user.role != "tenant":
        return error("You do not have permission to access this resource", 403)

    tenant = Tenant.query.filter_by(user_id=user.id).first()
    if not tenant:
        return error("No tenant record is linked to your account", 404)
    return {"tenant": tenant.to_dict()}, 200


@tenants_bp.route("/<int:tenant_id>", methods=["GET"])
def get_tenant(tenant_id):
    user = current_user()
    if not user:
        return error("User not found", 404)

    tenant = get_visible_tenant(user, tenant_id)
    if not tenant:
        # Same answer whether it is missing or belongs to someone else.
        return error("Tenant not found", 404)
    return {"tenant": tenant.to_dict()}, 200


@tenants_bp.route("/<int:tenant_id>", methods=["PUT"])
def update_tenant(tenant_id):
    user = current_user()
    if not user:
        return error("User not found", 404)

    tenant = get_visible_tenant(user, tenant_id)
    if not tenant:
        return error("Tenant not found", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return error("Request body must be valid JSON with at least one field", 400)

    allowed = MANAGER_EDITABLE if user.role in MANAGER_ROLES else TENANT_EDITABLE
    forbidden = set(data) - allowed
    if forbidden:
        return error(
            "You cannot change: " + ", ".join(sorted(forbidden)), 403
        )

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return error("Name cannot be empty", 400)
        tenant.name = name

    if "email" in data:
        email = clean_email(data["email"])
        if not email:
            return error("A valid email address is required", 400)
        duplicate = Tenant.query.filter_by(
            landlord_id=tenant.landlord_id, email=email
        ).first()
        if duplicate and duplicate.id != tenant.id:
            return error("Another tenant already uses this email", 409)
        tenant.email = email

    if "phone" in data:
        tenant.phone = (data["phone"] or "").strip() or None

    if "user_id" in data:
        problem = validate_user_link(data["user_id"], tenant)
        if problem:
            return problem
        tenant.user_id = data["user_id"]

    db.session.commit()
    return {"message": "Tenant updated", "tenant": tenant.to_dict()}, 200


def tenant_has_leases(tenant):
    """True if a lease points at this tenant.

    The Lease model lives in David's branch. Until it is merged there is
    nothing to check, so this returns False when the model does not exist.
    """
    lease_model = db.Model.registry._class_registry.get("Lease")
    if lease_model is None:
        return False
    return (
        db.session.query(lease_model.id)
        .filter(lease_model.tenant_id == tenant.id)
        .first()
        is not None
    )


@tenants_bp.route("/<int:tenant_id>", methods=["DELETE"])
def delete_tenant(tenant_id):
    user = current_user()
    if not user:
        return error("User not found", 404)
    if user.role not in MANAGER_ROLES:
        return error("You do not have permission to access this resource", 403)

    tenant = get_visible_tenant(user, tenant_id)
    if not tenant:
        return error("Tenant not found", 404)

    if tenant_has_leases(tenant):
        return error(
            "This tenant has leases and cannot be deleted. End or remove the leases first.",
            409,
        )

    db.session.delete(tenant)
    db.session.commit()
    return {"message": "Tenant deleted"}, 200
