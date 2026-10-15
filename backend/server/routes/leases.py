from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.extensions import db
from server.helpers import parse_decimal, parse_int
from server.models import Property, User
from server.models_tenant import Tenant
from server.models_unit_lease import LEASE_STATUSES, Lease, Unit
from server.pagination import get_pagination, pagination_metadata

leases_bp = Blueprint("leases_bp", __name__, url_prefix="/api/leases")
MANAGER_ROLES = {"landlord", "admin"}


def current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def accessible_unit_query(user):
    query = Unit.query.join(Property)
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query


def accessible_lease_query(user):
    query = Lease.query.join(Unit).join(Property)
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query


def tenant_is_accessible(user, tenant_id):
    query = Tenant.query.filter_by(id=tenant_id)
    if user.role != "admin":
        query = query.filter_by(landlord_id=user.id)
    return query.first()


def lease_payload(lease):
    return lease.to_dict()


def parse_lease_data(data, partial=False):
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object"
    allowed = {
        "unit_id", "tenant_id", "start_date", "end_date", "monthly_rent",
        "deposit", "deposit_amount", "status",
    }
    unknown = set(data) - allowed
    if unknown:
        return None, "Unsupported fields: " + ", ".join(sorted(unknown))
    values = {}
    if "unit_id" in data:
        unit_id, error = parse_int(data["unit_id"], "unit_id", maximum=2**31 - 1)
        if error or unit_id < 1:
            return None, error or "unit_id must be positive"
        values["unit_id"] = unit_id
    elif not partial:
        return None, "unit_id is required"
    if "tenant_id" in data:
        tenant_id, error = parse_int(data["tenant_id"], "tenant_id", maximum=2**31 - 1)
        if error or tenant_id < 1:
            return None, error or "tenant_id must be positive"
        values["tenant_id"] = tenant_id
    elif not partial:
        return None, "tenant_id is required"
    for field in ("start_date", "end_date"):
        if field in data:
            try:
                values[field] = date.fromisoformat(data[field])
            except (TypeError, ValueError):
                return None, f"{field} must be a date in YYYY-MM-DD format"
        elif not partial:
            return None, f"{field} is required"
    for field in ("monthly_rent", "deposit", "deposit_amount"):
        if field in data:
            value, error = parse_decimal(data[field], field)
            if error:
                return None, error
            values["deposit" if field == "deposit_amount" else field] = value
    if not partial and "monthly_rent" not in values:
        return None, "monthly_rent is required"
    if not partial and "deposit" not in values:
        values["deposit"] = 0
    if "status" in data:
        if data["status"] not in LEASE_STATUSES:
            return None, f"status must be one of: {', '.join(LEASE_STATUSES)}"
        values["status"] = data["status"]
    elif not partial:
        values["status"] = "active"
    if "start_date" in values and "end_date" in values:
        if values["end_date"] < values["start_date"]:
            return None, "end_date must be on or after start_date"
    return values, None


@leases_bp.route("/leases", methods=["GET"])
@jwt_required()
def list_leases():
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    query = accessible_lease_query(user)
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        if not tenant:
            return jsonify({"leases": [], "pagination": None}), 200
        query = query.filter(Lease.tenant_id == tenant.id)
    elif user.role not in MANAGER_ROLES:
        return jsonify({"error": "You do not have permission to view leases"}), 403

    for key, column in (("tenant_id", Lease.tenant_id), ("unit_id", Lease.unit_id)):
        raw = request.args.get(key)
        if raw is not None:
            try:
                value = int(raw)
            except ValueError:
                return jsonify({"error": f"{key} must be a positive integer"}), 400
            if value < 1:
                return jsonify({"error": f"{key} must be a positive integer"}), 400
            query = query.filter(column == value)
    status = request.args.get("status")
    if status:
        if status not in LEASE_STATUSES:
            return jsonify({"error": "Invalid lease status"}), 400
        query = query.filter(Lease.status == status)
    pagination, error = get_pagination()
    if error:
        return jsonify({"error": error}), 400
    page, per_page = pagination
    result = query.order_by(Lease.created_at.desc(), Lease.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        "leases": [lease_payload(lease) for lease in result.items],
        "pagination": pagination_metadata(result),
    }), 200


@leases_bp.route("/leases", methods=["POST"])
@jwt_required()
def create_lease():
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "Only landlords and admins can create leases"}), 403
    values, error = parse_lease_data(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400
    unit = accessible_unit_query(user).filter(Unit.id == values["unit_id"]).first()
    if not unit:
        return jsonify({"error": "Unit not found"}), 404
    if not tenant_is_accessible(user, values["tenant_id"]):
        return jsonify({"error": "Tenant not found"}), 404
    if values["status"] == "active":
        overlap = Lease.query.filter(
            Lease.unit_id == unit.id,
            Lease.status == "active",
            Lease.start_date <= values["end_date"],
            Lease.end_date >= values["start_date"],
        ).first()
        if overlap:
            return jsonify({"error": "Unit is already leased during this timeframe"}), 409
    lease = Lease(**values)
    db.session.add(lease)
    db.session.commit()
    return jsonify(lease_payload(lease)), 201


@leases_bp.route("/leases/<int:lease_id>", methods=["GET"])
@jwt_required()
def get_lease(lease_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES and user.role != "tenant":
        return jsonify({"error": "You do not have permission to view leases"}), 403
    query = accessible_lease_query(user).filter(Lease.id == lease_id)
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        query = query.filter(Lease.tenant_id == tenant.id if tenant else False)
    lease = query.first()
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    return jsonify(lease_payload(lease)), 200


@leases_bp.route("/leases/<int:lease_id>", methods=["PUT"])
@jwt_required()
def update_lease(lease_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "Only landlords and admins can update leases"}), 403
    lease = accessible_lease_query(user).filter(Lease.id == lease_id).first()
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    values, error = parse_lease_data(request.get_json(silent=True), partial=True)
    if error:
        return jsonify({"error": error}), 400
    if "unit_id" in values and values["unit_id"] != lease.unit_id:
        return jsonify({"error": "A lease cannot be moved to another unit"}), 400
    if "tenant_id" in values and not tenant_is_accessible(user, values["tenant_id"]):
        return jsonify({"error": "Tenant not found"}), 404
    start_date = values.get("start_date", lease.start_date)
    end_date = values.get("end_date", lease.end_date)
    status = values.get("status", lease.status)
    if status == "active":
        overlap = Lease.query.filter(
            Lease.unit_id == lease.unit_id,
            Lease.id != lease.id,
            Lease.status == "active",
            Lease.start_date <= end_date,
            Lease.end_date >= start_date,
        ).first()
        if overlap:
            return jsonify({"error": "Unit is already leased during this timeframe"}), 409
    for field, value in values.items():
        setattr(lease, field, value)
    db.session.commit()
    return jsonify(lease_payload(lease)), 200


@leases_bp.route("/leases/<int:lease_id>", methods=["DELETE"])
@jwt_required()
def delete_lease(lease_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "Only landlords and admins can delete leases"}), 403
    lease = accessible_lease_query(user).filter(Lease.id == lease_id).first()
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    lease.status = "terminated"
    db.session.commit()
    return jsonify({"message": "Lease terminated successfully"}), 200
