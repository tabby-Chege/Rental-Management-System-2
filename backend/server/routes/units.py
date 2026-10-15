import math
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.extensions import db
from server.models import Property, User
from server.models_unit_lease import Lease, Unit
from server.pagination import get_pagination, pagination_metadata

units_bp = Blueprint("units_bp", __name__, url_prefix="/api/units")
MANAGER_ROLES = {"landlord", "admin"}

def current_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    return db.session.get(User, user_id)

def accessible_property(user, property_id):
    query = Property.query.filter_by(id=property_id)
    if user.role != "admin":
        query = query.filter_by(owner_id=user.id)
    return query.first()

def accessible_unit(user, unit_id):
    query = Unit.query.join(Property).filter(Unit.id == unit_id)
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query.first()

def validate_unit_data(data, partial=False):
    if not isinstance(data, dict) or (not partial and not data):
        return None, "Request body must be a JSON object with unit fields"

    allowed = {"unit_number", "bedrooms", "bathrooms", "rent_amount"}
    unknown = set(data) - allowed
    if unknown:
        return None, "Unsupported fields: " + ", ".join(sorted(unknown))

    cleaned = {}
    if "unit_number" in data:
        value = data["unit_number"]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 50:
            return None, "unit_number must be non-empty text of at most 50 characters"
        cleaned["unit_number"] = value.strip()
    elif not partial:
        return None, "unit_number is required"

    if "bedrooms" in data:
        value = data["bedrooms"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None, "bedrooms must be a non-negative integer"
        cleaned["bedrooms"] = value
    elif not partial:
        cleaned["bedrooms"] = 1

    if "bathrooms" in data:
        value = data["bathrooms"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            return None, "bathrooms must be a non-negative number"
        cleaned["bathrooms"] = value
    elif not partial:
        cleaned["bathrooms"] = 1.0

    if "rent_amount" in data:
        value = data["rent_amount"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            return None, "rent_amount must be a positive finite number"
        cleaned["rent_amount"] = value
    elif not partial:
        return None, "rent_amount is required"

    return cleaned, None

@units_bp.route("/properties/<int:property_id>/units", methods=["GET"])
@jwt_required()
def get_property_units(property_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "You do not have permission to view units"}), 403

    prop = accessible_property(user, property_id)
    if not prop:
        return jsonify({"error": "Property not found"}), 404

    pagination, error = get_pagination()
    if error:
        return jsonify({"error": error}), 400
    page, per_page = pagination

    result = (
        Unit.query.filter_by(property_id=property_id)
        .order_by(Unit.unit_number, Unit.id)
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return jsonify({
        "units": [unit.to_dict() for unit in result.items],
        "pagination": pagination_metadata(result),
    }), 200

@units_bp.route("/properties/<int:property_id>/units", methods=["POST"])
@jwt_required()
def create_unit(property_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "You do not have permission to create units"}), 403

    prop = accessible_property(user, property_id)
    if not prop:
        return jsonify({"error": "Property not found"}), 404

    data, error = validate_unit_data(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    unit = Unit(property_id=prop.id, is_occupied=False, **data)
    db.session.add(unit)
    db.session.commit()
    return jsonify(unit.to_dict()), 201

@units_bp.route("/units/<int:unit_id>", methods=["PUT"])
@jwt_required()
def update_unit(unit_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "You do not have permission to update units"}), 403

    unit = accessible_unit(user, unit_id)
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

    data, error = validate_unit_data(request.get_json(silent=True), partial=True)
    if error:
        return jsonify({"error": error}), 400

    for field, value in data.items():
        setattr(unit, field, value)

    db.session.commit()
    return jsonify(unit.to_dict()), 200

@units_bp.route("/units/<int:unit_id>", methods=["DELETE"])
@jwt_required()
def delete_unit(unit_id):
    user = current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "You do not have permission to delete units"}), 403

    unit = accessible_unit(user, unit_id)
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

    if Lease.query.filter_by(unit_id=unit.id).first():
        return jsonify({"error": "Units with lease records cannot be deleted"}), 409

    db.session.delete(unit)
    db.session.commit()
    return jsonify({"message": "Unit deleted successfully"}), 200