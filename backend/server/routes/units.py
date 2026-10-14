from flask import Blueprint, request

from server.extensions import db
from server.helpers import current_manager, error, is_id, parse_decimal, parse_int
from server.models_unit_lease import Lease, Unit, current_leases
from server.ownership import get_owned_property, get_owned_unit, owned_units_query

units_bp = Blueprint("units", __name__, url_prefix="/api/units")

EDITABLE = {"unit_number", "bedrooms", "bathrooms", "rent_amount"}

# Optional numeric fields and how to validate each one.
OPTIONAL_FIELDS = {
    "bedrooms": lambda v: parse_int(v, "Bedrooms"),
    "bathrooms": lambda v: parse_decimal(v, "Bathrooms", places="0.1", maximum="99.9"),
    "rent_amount": lambda v: parse_decimal(v, "Rent amount"),
}


def read_optional_fields(data):
    """Validate the optional fields present in data: (fields, None) or (None, error_response)."""
    fields = {}
    for name, parse in OPTIONAL_FIELDS.items():
        if name not in data:
            continue
        if data[name] is None or data[name] == "":
            fields[name] = None
            continue
        value, message = parse(data[name])
        if message:
            return None, error(message, 400)
        fields[name] = value
    return fields, None


def read_unit_number(value):
    """Return (unit_number, None) or (None, message)."""
    unit_number = str(value if value is not None else "").strip()
    if not unit_number:
        return None, "Unit number is required"
    if len(unit_number) > 50:
        return None, "Unit number must be 50 characters or fewer"
    return unit_number, None


def unit_response(unit):
    return unit.to_dict(current_lease=current_leases([unit.id]).get(unit.id))


@units_bp.route("", methods=["GET"])
def list_units():
    user, problem = current_manager()
    if problem:
        return problem

    query = owned_units_query(user)
    raw_property_id = request.args.get("property_id")
    if raw_property_id is not None:
        if not raw_property_id.isdigit():
            return error("property_id must be a number", 400)
        query = query.filter(Unit.property_id == int(raw_property_id))

    units = query.order_by(Unit.property_id, Unit.unit_number).all()
    leases = current_leases([unit.id for unit in units])
    return {"units": [unit.to_dict(current_lease=leases.get(unit.id)) for unit in units]}, 200


@units_bp.route("", methods=["POST"])
def create_unit():
    user, problem = current_manager()
    if problem:
        return problem

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Request body must be valid JSON", 400)

    property_id = data.get("property_id")
    if not is_id(property_id):
        return error("property_id is required", 400)

    unit_number, message = read_unit_number(data.get("unit_number"))
    if message:
        return error(message, 400)

    fields, problem = read_optional_fields(data)
    if problem:
        return problem

    if not get_owned_property(user, property_id):
        # Same answer whether it is missing or belongs to someone else.
        return error("Property not found", 404)

    if Unit.query.filter_by(property_id=property_id, unit_number=unit_number).first():
        return error("This property already has a unit with that number", 409)

    unit = Unit(property_id=property_id, unit_number=unit_number, **fields)
    db.session.add(unit)
    db.session.commit()
    return {"message": "Unit created", "unit": unit.to_dict()}, 201


@units_bp.route("/<int:unit_id>", methods=["GET"])
def get_unit(unit_id):
    user, problem = current_manager()
    if problem:
        return problem

    unit = get_owned_unit(user, unit_id)
    if not unit:
        return error("Unit not found", 404)
    return {"unit": unit_response(unit)}, 200


@units_bp.route("/<int:unit_id>", methods=["PUT"])
def update_unit(unit_id):
    user, problem = current_manager()
    if problem:
        return problem

    unit = get_owned_unit(user, unit_id)
    if not unit:
        return error("Unit not found", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return error("Request body must be valid JSON with at least one field", 400)

    forbidden = set(data) - EDITABLE
    if forbidden:
        return error("You cannot change: " + ", ".join(sorted(forbidden)), 403)

    fields, problem = read_optional_fields(data)
    if problem:
        return problem

    if "unit_number" in data:
        unit_number, message = read_unit_number(data["unit_number"])
        if message:
            return error(message, 400)
        duplicate = Unit.query.filter_by(
            property_id=unit.property_id, unit_number=unit_number
        ).first()
        if duplicate and duplicate.id != unit.id:
            return error("This property already has a unit with that number", 409)
        unit.unit_number = unit_number

    for name, value in fields.items():
        setattr(unit, name, value)

    db.session.commit()
    return {"message": "Unit updated", "unit": unit_response(unit)}, 200


@units_bp.route("/<int:unit_id>", methods=["DELETE"])
def delete_unit(unit_id):
    user, problem = current_manager()
    if problem:
        return problem

    unit = get_owned_unit(user, unit_id)
    if not unit:
        return error("Unit not found", 404)

    if Lease.query.filter_by(unit_id=unit.id).first():
        return error("This unit has leases and cannot be deleted. Remove its leases first.", 409)

    db.session.delete(unit)
    db.session.commit()
    return {"message": "Unit deleted"}, 200