from datetime import date
from decimal import Decimal
import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.extensions import db
from server.models import Property, User
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit

leases_bp = Blueprint("leases_bp", __name__, url_prefix="/api/leases")

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

@leases_bp.route("", methods=["POST"])
@jwt_required()
def create_lease():
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "Only landlords and admins can create leases"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required_fields = {
        "unit_id",
        "tenant_id",
        "start_date",
        "end_date",
        "monthly_rent",
        "deposit_amount",
    }
    if not required_fields.issubset(data):
        return jsonify({"error": "Missing required lease fields"}), 400

    unit_id = data["unit_id"]
    tenant_id = data["tenant_id"]

    unit = accessible_unit_query(user).filter(Unit.id == unit_id).first()
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

    try:
        start_date = date.fromisoformat(data["start_date"])
        end_date = date.fromisoformat(data["end_date"])
    except ValueError:
        return jsonify({"error": "Dates must use YYYY-MM-DD format"}), 400

    if start_date >= end_date:
        return jsonify({"error": "End date must occur after start date"}), 400

    monthly_rent = data["monthly_rent"]
    deposit_amount = data["deposit_amount"]

    overlapping_lease = Lease.query.filter(
        Lease.unit_id == unit_id,
        Lease.is_active == True,
        Lease.start_date <= end_date,
        Lease.end_date >= start_date,
    ).first()

    if overlapping_lease:
        return jsonify({"error": "Unit is already leased during this timeframe"}), 409

    lease = Lease(
        unit_id=unit_id,
        tenant_id=tenant_id,
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

@leases_bp.route("/<int:lease_id>", methods=["DELETE"])
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
        Lease.is_active == True,
    ).first()
    
    if not has_other_active_lease:
        unit = db.session.get(Unit, lease.unit_id)
        if unit:
            unit.is_occupied = False

    db.session.commit()
    return jsonify({"message": "Lease terminated successfully"}), 200