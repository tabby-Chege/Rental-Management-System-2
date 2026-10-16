import math

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Property, User
from server.models_unit_lease import Lease, Unit, current_leases
from server.pagination import get_pagination, pagination_metadata


units_bp = Blueprint("units_bp", __name__, url_prefix="/api")
MANAGER_ROLES = {"landlord", "admin"}
UNIT_FIELDS = {"unit_number", "bedrooms", "bathrooms", "rent_amount"}


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


def accessible_units_query(user):
    query = Unit.query.join(Property, Unit.property_id == Property.id)
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query


def accessible_unit(user, unit_id):
    return accessible_units_query(user).filter(Unit.id == unit_id).first()


def validate_unit_data(data, partial=False):
    if not isinstance(data, dict) or (partial and not data):
        return None, "Request body must be a JSON object with unit fields"

    unknown = set(data) - UNIT_FIELDS
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

    for field in ("bedrooms", "bathrooms", "rent_amount"):
        if field not in data:
            if not partial:
                cleaned[field] = None
            continue

        value = data[field]
        if value is None and field != "bedrooms":
            cleaned[field] = None
            continue
        if field == "bedrooms":
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                return None, "bedrooms must be a non-negative integer or null"
            cleaned[field] = value
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            return None, f"{field} must be a non-negative finite number or null"
        cleaned[field] = value

    return cleaned, None


def unit_json(unit):
    return unit.to_dict(current_leases([unit.id]).get(unit.id))


def list_units_response(user, property_id=None):
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to view units"}, 403

    query = accessible_units_query(user)
    if property_id is not None:
        if not accessible_property(user, property_id):
            return {"error": "Property not found"}, 404
        query = query.filter(Unit.property_id == property_id)
    elif request.args.get("property_id"):
        raw_property_id = request.args["property_id"]
        if not raw_property_id.isdecimal() or int(raw_property_id) < 1:
            return {"error": "property_id must be a positive integer"}, 400
        property_id = int(raw_property_id)
        if not accessible_property(user, property_id):
            return {"error": "Property not found"}, 404
        query = query.filter(Unit.property_id == property_id)

    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    result = query.order_by(Unit.unit_number, Unit.id).paginate(
        page=page, per_page=per_page, error_out=False
    )
    occupancy = current_leases([unit.id for unit in result.items])
    return {
        "units": [unit.to_dict(occupancy.get(unit.id)) for unit in result.items],
        "pagination": pagination_metadata(result),
    }, 200


@units_bp.route("/units", methods=["GET"])
@jwt_required()
def get_units():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    return list_units_response(user)


@units_bp.route("/properties/<int:property_id>/units", methods=["GET"])
@jwt_required()
def get_property_units(property_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    return list_units_response(user, property_id)


def create_unit_record(user, property_id, data):
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to create units"}, 403
    prop = accessible_property(user, property_id)
    if not prop:
        return {"error": "Property not found"}, 404
    cleaned, error = validate_unit_data(data)
    if error:
        return {"error": error}, 400

    unit = Unit(property_id=prop.id, **cleaned)
    db.session.add(unit)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "That unit number already exists for this property"}, 409

    serialized = unit_json(unit)
    return {"unit": serialized, **serialized}, 201


@units_bp.route("/units", methods=["POST"])
@jwt_required()
def create_unit():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    property_id = data.get("property_id")
    if isinstance(property_id, bool) or not isinstance(property_id, int) or property_id < 1:
        return {"error": "property_id must be a positive integer"}, 400
    return create_unit_record(
        user, property_id, {field: value for field, value in data.items() if field != "property_id"}
    )
@units_bp.route("/properties/<int:property_id>/units", methods=["POST"])
@jwt_required()
def create_property_unit(property_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    return create_unit_record(user, property_id, request.get_json(silent=True))


@units_bp.route("/units/<int:unit_id>", methods=["GET"])
@jwt_required()
def get_unit(unit_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to view units"}, 403
    unit = accessible_unit(user, unit_id)
    if not unit:
        return {"error": "Unit not found"}, 404
    serialized = unit_json(unit)
    return {"unit": serialized, **serialized}, 200

@units_bp.route("/units/<int:unit_id>", methods=["PUT"])
@jwt_required()
def update_unit(unit_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to update units"}, 403
    unit = accessible_unit(user, unit_id)
    if not unit:
        return {"error": "Unit not found"}, 404
    cleaned, error = validate_unit_data(request.get_json(silent=True), partial=True)
    if error:
        return {"error": error}, 400

    for field, value in cleaned.items():
        setattr(unit, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "That unit number already exists for this property"}, 409
    serialized = unit_json(unit)
    return {"unit": serialized, **serialized}, 200

@units_bp.route("/units/<int:unit_id>", methods=["DELETE"])
@jwt_required()
def delete_unit(unit_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to delete units"}, 403
    unit = accessible_unit(user, unit_id)
    if not unit:
        return {"error": "Unit not found"}, 404
    if Lease.query.filter_by(unit_id=unit.id).first():
        return {"error": "Units with lease records cannot be deleted"}, 409

    db.session.delete(unit)
    db.session.commit()
    return {"message": "Unit deleted successfully"}, 200
