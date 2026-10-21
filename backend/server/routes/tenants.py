from datetime import date
import re

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import inspect, text

from server.extensions import db
from server.models import Property, User
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit
from server.occupancy import property_json, property_occupancy
from server.pagination import get_pagination, pagination_metadata

tenants_bp = Blueprint("tenants", __name__, url_prefix="/api/tenants")

MANAGER_ROLES = {"landlord", "admin"}
# Fields a tenant may change on their own record.
TENANT_EDITABLE = {"email", "phone"}
MANAGER_EDITABLE = {"name", "email", "phone"}


def error(message, status):
    return {"error": message}, status


def current_user():
    verify_jwt_in_request()
    return db.session.get(User, int(get_jwt_identity()))


def clean_email(value):
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return None
    return email


def clean_phone(value):
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "Phone must use international E.164 format, such as +254712345678"
    phone = value.strip()
    if not phone:
        return None, None
    if not re.fullmatch(r"\+[1-9]\d{6,14}", phone):
        return None, "Phone must use international E.164 format, such as +254712345678"
    return phone, None


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

    pagination, pagination_error = get_pagination()
    if pagination_error:
        return error(pagination_error, 400)

    page, per_page = pagination
    result = (
        Tenant.query.filter_by(landlord_id=user.id)
        .order_by(Tenant.name, Tenant.id)
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return {
        "tenants": [tenant.to_dict() for tenant in result.items],
        "pagination": pagination_metadata(result),
    }, 200


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

    today = date.today()
    leases = (
        Lease.query.filter(
            Lease.tenant_id == tenant.id,
            Lease.status == "active",
            Lease.start_date <= today,
            Lease.end_date >= today,
        )
        .order_by(Lease.start_date.desc(), Lease.id.desc())
        .all()
    )
    residences = []
    for lease in leases:
        unit = db.session.get(Unit, lease.unit_id)
        prop = db.session.get(Property, unit.property_id) if unit else None
        landlord = db.session.get(User, prop.owner_id) if prop else None
        if not unit or not prop:
            continue
        residences.append({
            "lease": lease.to_dict(),
            "unit": unit.to_dict(lease),
            "property": property_json(prop, property_occupancy([prop])[prop.id]),
            "landlord": (
                {"name": landlord.name, "email": landlord.email}
                if landlord
                else None
            ),
        })

    return {
        "tenant": tenant.to_dict(),
        "current_residences": residences,
    }, 200


@tenants_bp.route("/me", methods=["PUT"])
def update_my_tenant_record():
    user = current_user()
    if not user:
        return error("User not found", 404)
    if user.role != "tenant":
        return error("You do not have permission to access this resource", 403)

    tenant = Tenant.query.filter_by(user_id=user.id).first()
    if not tenant:
        return error("No tenant record is linked to your account", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return error("Request body must be valid JSON with at least one field", 400)
    forbidden = set(data) - TENANT_EDITABLE
    if forbidden:
        return error("You cannot change: " + ", ".join(sorted(forbidden)), 403)

    if "email" in data:
        email = clean_email(data["email"])
        if not email:
            return error("A valid email address is required", 400)
        if len(email) > 120:
            return error("Email is too long", 400)
        duplicate = Tenant.query.filter_by(
            landlord_id=tenant.landlord_id, email=email
        ).first()
        if duplicate and duplicate.id != tenant.id:
            return error("Another tenant already uses this email", 409)
        tenant.email = email

    if "phone" in data:
        phone, phone_error = clean_phone(data["phone"])
        if phone_error:
            return error(phone_error, 400)
        tenant.phone = phone

    db.session.commit()
    return {"message": "Tenant details updated", "tenant": tenant.to_dict()}, 200


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
        if not isinstance(data["name"], str):
            return error("Name must be text", 400)
        name = data["name"].strip()
        if not name:
            return error("Name cannot be empty", 400)
        if len(name) > 120:
            return error("Name is too long", 400)
        tenant.name = name

    if "email" in data:
        email = clean_email(data["email"])
        if not email:
            return error("A valid email address is required", 400)
        if len(email) > 120:
            return error("Email is too long", 400)
        duplicate = Tenant.query.filter_by(
            landlord_id=tenant.landlord_id, email=email
        ).first()
        if duplicate and duplicate.id != tenant.id:
            return error("Another tenant already uses this email", 409)
        tenant.email = email

    if "phone" in data:
        phone, phone_error = clean_phone(data["phone"])
        if phone_error:
            return error(phone_error, 400)
        tenant.phone = phone

    db.session.commit()
    return {"message": "Tenant updated", "tenant": tenant.to_dict()}, 200


def tenant_has_leases(tenant):
    """Check for leases without requiring the optional leases module to load."""
    if not inspect(db.engine).has_table("leases"):
        return False
    return db.session.execute(
        text("SELECT 1 FROM leases WHERE tenant_id = :tenant_id LIMIT 1"),
        {"tenant_id": tenant.id},
    ).first() is not None


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
