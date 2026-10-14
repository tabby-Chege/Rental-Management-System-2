import math
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.extensions import db
from server.models import Property, User
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit


leases_bp = Blueprint("leases_bp", __name__)
MANAGER_ROLES = {"landlord", "admin"}


def current_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    return db.session.get(User, user_id)


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


@leases_bp.route("/leases", methods=["POST"])
@jwt_required()
def create_lease():
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "Only landlords and admins can create leases"}), 403

    data = request.get_json(silent=True)
    required_fields = {
        "unit_id",
        "tenant_id",
        "start_date",
        "end_date",
        "monthly_rent",
        "deposit_amount",
    }
    if not isinstance(data, dict) or not required_fields.issubset(data):
        return jsonify({"error": "Missing required lease fields"}), 400

    unit_id = data["unit_id"]
    tenant_id = data["tenant_id"]
    if (
        isinstance(unit_id, bool)
        or not isinstance(unit_id, int)
        or isinstance(tenant_id, bool)
        or not isinstance(tenant_id, int)
    ):
        return jsonify({"error": "unit_id and tenant_id must be integers"}), 400

    unit = accessible_unit_query(user).filter(Unit.id == unit_id).first()
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

    property_record = db.session.get(Property, unit.property_id)
    tenant = db.session.get(Tenant, tenant_id)
    property_owner = property_record.owner_id if property_record else None
    if not tenant or tenant.landlord_id != property_owner:
        return jsonify({"error": "Tenant not found for this property owner"}), 404

    try:
        start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return jsonify({"error": "Dates must use YYYY-MM-DD format"}), 400

    if start_date >= end_date:
        return jsonify({"error": "End date must occur after start date"}), 400

    monthly_rent = data["monthly_rent"]
    deposit_amount = data["deposit_amount"]
    for field, value, allow_zero in (
        ("monthly_rent", monthly_rent, False),
        ("deposit_amount", deposit_amount, True),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or (not allow_zero and value == 0)
        ):
            return jsonify({"error": f"{field} must be a valid non-negative amount"}), 400

    overlapping_lease = Lease.query.filter(
        Lease.unit_id == unit_id,
        Lease.is_active.is_(True),
        Lease.start_date <= end_date,
        Lease.end_date >= start_date,
    ).first()
    if overlapping_lease:
        return jsonify({
            "error": "Unit is already leased during this timeframe"
        }), 409

    lease = Lease(
        unit_id=unit.id,
        tenant_id=tenant.id,
        start_date=start_date,
        end_date=end_date,
        monthly_rent=monthly_rent,
        deposit_amount=deposit_amount,
        is_active=True,
    )
    unit.is_occupied = True
    db.session.add(lease)
    db.session.commit()
    return jsonify(lease.to_dict()), 201


@leases_bp.route("/leases/<int:lease_id>", methods=["DELETE"])
@jwt_required()
def terminate_lease(lease_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "Only landlords and admins can end leases"}), 403

    lease = accessible_lease_query(user).filter(Lease.id == lease_id).first()
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    lease.is_active = False
    has_other_active_lease = Lease.query.filter(
        Lease.unit_id == lease.unit_id,
        Lease.id != lease.id,
        Lease.is_active.is_(True),
    ).first()
    if not has_other_active_lease:
        lease.unit.is_occupied = False

    db.session.commit()
    return jsonify({"message": "Lease terminated successfully"}), 200
