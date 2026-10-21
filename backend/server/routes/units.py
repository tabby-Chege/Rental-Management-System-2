import math
from datetime import date

from sqlalchemy import exists, or_
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Property, User
from server.models_media import PropertyPhoto
from server.models_application import Application, RESERVED_APPLICATION_STATUSES
from server.models_unit_lease import Lease, Room, Unit
from server.occupancy import unit_occupancy
from server.pagination import get_pagination, pagination_metadata
from server.reservations import process_reservations
from server.unit_validation import validate_unit_data


units_bp = Blueprint("units_bp", __name__, url_prefix="/api")
MANAGER_ROLES = {"landlord", "admin"}
MAX_BULK_UNITS = 500


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


def unit_json(unit):
    status = unit_occupancy([unit.id])[unit.id]
    return unit.to_dict(status["lease"], status["is_reserved"])


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
    occupancy = unit_occupancy(unit.id for unit in result.items)
    return {
        "units": [
            unit.to_dict(
                occupancy[unit.id]["lease"],
                occupancy[unit.id]["is_reserved"],
            )
            for unit in result.items
        ],
        "pagination": pagination_metadata(result),
    }, 200


@units_bp.route("/units/public", methods=["GET"])
def list_public_units():
    process_reservations()
    query = Unit.query.join(Property, Unit.property_id == Property.id)

    location = request.args.get("location", "").strip()
    search = request.args.get("q", "").strip()
    unit_type = request.args.get("unit_type", "").strip()
    if len(location) > 120 or len(search) > 120:
        return {"error": "Search terms must be 120 characters or fewer"}, 400
    if len(unit_type) > 50:
        return {"error": "unit_type must be 50 characters or fewer"}, 400
    for search_term in (location, search):
        if search_term:
            pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    Property.name.ilike(pattern),
                    Property.address.ilike(pattern),
                    Property.city.ilike(pattern),
                    Property.state.ilike(pattern),
                    Property.zip_code.ilike(pattern),
                )
            )
    if unit_type:
        query = query.filter(Unit.unit_type.ilike(unit_type))

    try:
        bedrooms = request.args.get("bedrooms")
        if bedrooms is not None:
            bedroom_count = int(bedrooms)
            if bedroom_count < 0:
                raise ValueError
            query = query.filter(Unit.bedrooms == bedroom_count)

        bathrooms = request.args.get("bathrooms")
        if bathrooms is not None:
            bathroom_count = float(bathrooms)
            if not math.isfinite(bathroom_count) or bathroom_count < 0:
                raise ValueError
            query = query.filter(Unit.bathrooms == bathroom_count)

        min_rent = request.args.get("min_rent")
        if min_rent is not None:
            min_rent_value = float(min_rent)
            if not math.isfinite(min_rent_value) or min_rent_value < 0:
                raise ValueError
            query = query.filter(Unit.rent_amount >= min_rent_value)

        max_rent = request.args.get("max_rent")
        if max_rent is not None:
            max_rent_value = float(max_rent)
            if not math.isfinite(max_rent_value) or max_rent_value < 0:
                raise ValueError
            query = query.filter(Unit.rent_amount <= max_rent_value)

        if (
            min_rent is not None
            and max_rent is not None
            and min_rent_value > max_rent_value
        ):
            return {"error": "min_rent must not exceed max_rent"}, 400
    except ValueError:
        return {
            "error": "bedrooms, bathrooms, and rent filters must be non-negative numbers"
        }, 400

    availability = request.args.get("availability", "vacant").strip().lower()
    if availability not in {"vacant", "reserved", "occupied", "all"}:
        return {"error": "availability must be vacant, reserved, occupied, or all"}, 400

    occupied_lease = exists().where(
        Lease.unit_id == Unit.id,
        Lease.status == "active",
        Lease.start_date <= date.today(),
        Lease.end_date >= date.today(),
    )
    approved_application = exists().where(
        Application.unit_id == Unit.id,
        Application.status.in_(RESERVED_APPLICATION_STATUSES),
    )
    if availability == "vacant":
        query = query.filter(~occupied_lease, ~approved_application)
    elif availability == "reserved":
        query = query.filter(~occupied_lease, approved_application)
    elif availability == "occupied":
        query = query.filter(occupied_lease)

    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    result = query.add_columns(
        Property.name,
        Property.address_line,
        Property.city,
        Property.region,
        Property.postal_code,
        Property.country,
        Property.time_zone,
    ).order_by(Property.name, Unit.unit_number, Unit.id).paginate(
        page=page, per_page=per_page, error_out=False
    )
    occupancy = unit_occupancy(row[0].id for row in result.items)
    unit_ids = [unit.id for unit, *_ in result.items]
    property_ids = {unit.property_id for unit, *_ in result.items}
    photos = (
        PropertyPhoto.query.filter(
            or_(
                PropertyPhoto.unit_id.in_(unit_ids),
                PropertyPhoto.property_id.in_(property_ids),
            )
        )
        .order_by(PropertyPhoto.is_cover.desc(), PropertyPhoto.id.asc())
        .all()
        if unit_ids
        else []
    )
    unit_photos = {}
    property_photos = {}
    for photo in photos:
        if photo.unit_id is not None:
            unit_photos.setdefault(photo.unit_id, photo)
        elif photo.property_id is not None:
            property_photos.setdefault(photo.property_id, photo)

    return {
        "units": [
            {
                **unit.to_dict(
                    occupancy[unit.id]["lease"],
                    occupancy[unit.id]["is_reserved"],
                ),
                "property_name": property_name,
                "property_address": property_address,
                "property_address_line": property_address,
                "property_city": property_city,
                "property_state": property_state,
                "property_region": property_state,
                "property_zip_code": property_zip_code,
                "property_postal_code": property_zip_code,
                "property_country": property_country,
                "property_time_zone": property_time_zone,
                "photo_url": (
                    unit_photos.get(unit.id) or property_photos.get(unit.property_id)
                ).to_dict()["url"]
                if unit_photos.get(unit.id) or property_photos.get(unit.property_id)
                else None,
            }
            for (
                unit,
                property_name,
                property_address,
                property_city,
                property_state,
                property_zip_code,
                property_country,
                property_time_zone,
            ) in result.items
        ],
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
    if prop.rental_type == "whole_property":
        return {"error": "Whole properties cannot have additional units"}, 409
    cleaned, error = validate_unit_data(
        data,
        currency=prop.currency,
        floors=prop.floors,
    )
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


@units_bp.route("/properties/<int:property_id>/units/bulk", methods=["POST"])
@jwt_required()
def bulk_create_property_units(property_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to create units"}, 403
    prop = accessible_property(user, property_id)
    if not prop:
        return {"error": "Property not found"}, 404
    if prop.rental_type == "whole_property":
        return {"error": "Whole properties cannot have additional units"}, 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be a JSON object"}, 400
    allowed_fields = {"units_per_floor", "layout", "rent_amount"}
    unknown = set(data) - allowed_fields
    if unknown:
        return {"error": "Unsupported fields: " + ", ".join(sorted(unknown))}, 400
    units_per_floor = data.get("units_per_floor")
    if (
        isinstance(units_per_floor, bool)
        or not isinstance(units_per_floor, int)
        or not 1 <= units_per_floor <= 99
    ):
        return {"error": "units_per_floor must be a whole number from 1 to 99"}, 400
    if "rent_amount" not in data or data["rent_amount"] is None:
        return {"error": "rent_amount is required"}, 400
    unit_count = units_per_floor * prop.floors
    if unit_count > MAX_BULK_UNITS:
        return {
            "error": f"Bulk creation cannot exceed {MAX_BULK_UNITS} units at a time"
        }, 400
    if not isinstance(data.get("layout"), str) or not data["layout"].strip():
        return {"error": "layout is required"}, 400

    layout = data["layout"].strip().lower()
    bedrooms = (
        0
        if layout == "studio"
        else int(layout.split("+", 1)[0])
        if "+" in layout and layout.split("+", 1)[0].isdigit()
        else None
    )
    unit_type = (
        "studio"
        if bedrooms == 0
        else f"{bedrooms}-bedroom"
        if bedrooms is not None
        else None
    )
    created_units = []
    for floor_number in range(1, prop.floors + 1):
        for sequence in range(1, units_per_floor + 1):
            values = {
                "unit_number": f"{floor_number}{sequence:02d}",
                "floor_number": floor_number,
                "layout": layout,
                "bedrooms": bedrooms,
                "unit_type": unit_type,
                "rent_amount": data["rent_amount"],
            }
            cleaned, error = validate_unit_data(
                values,
                currency=prop.currency,
                floors=prop.floors,
            )
            if error:
                return {"error": error}, 400
            created_units.append(Unit(property_id=prop.id, **cleaned))

    db.session.add_all(created_units)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {
            "error": "Bulk creation conflicts with one or more existing unit numbers; no units were added"
        }, 409

    return {
        "message": f"Created {len(created_units)} units",
        "units": [unit.to_dict() for unit in created_units],
        "created_count": len(created_units),
    }, 201


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
    cleaned, error = validate_unit_data(
        request.get_json(silent=True),
        defaults={
            "unit_number": unit.unit_number,
            "unit_type": unit.unit_type,
            "bedrooms": unit.bedrooms,
            "bathrooms": unit.bathrooms,
            "rent_amount": unit.rent_amount,
            "floor_number": unit.floor_number,
            "layout": unit.layout,
            "size": unit.size,
            "size_unit": unit.size_unit,
            "furnished": unit.furnished,
            "description": unit.description,
        },
        partial=True,
        currency=unit.property.currency,
        floors=unit.property.floors,
    )
    if error:
        return {"error": error}, 400

    if (
        unit.property.rental_type == "whole_property"
        and cleaned["unit_number"] != "Entire property"
    ):
        return {"error": "The whole-property unit must remain named Entire property"}, 409

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
    if unit.property.rental_type == "whole_property":
        return {"error": "The only unit of a whole property cannot be deleted"}, 409
    if Lease.query.filter_by(unit_id=unit.id).first():
        return {"error": "Units with lease records cannot be deleted"}, 409

    db.session.delete(unit)
    db.session.commit()
    return {"message": "Unit deleted successfully"}, 200


ROOM_TYPES = {"bedroom", "living_room", "kitchen", "bathroom", "balcony", "other"}
ROOM_FIELDS = {"name", "room_type", "size", "size_unit", "description"}


def clean_room_data(data, *, partial=False, defaults=None):
    if not isinstance(data, dict) or (partial and not data):
        return None, "Request body must be a JSON object with room fields"
    unknown = set(data) - ROOM_FIELDS
    if unknown:
        return None, "Unsupported fields: " + ", ".join(sorted(unknown))
    cleaned = dict(defaults or {})
    if not partial or "name" in data:
        name = data.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            return None, "name must be non-empty text of at most 80 characters"
        cleaned["name"] = name.strip()
    if not partial or "room_type" in data:
        room_type = data.get("room_type")
        if not isinstance(room_type, str) or room_type not in ROOM_TYPES:
            return None, "room_type must be bedroom, living_room, kitchen, bathroom, balcony, or other"
        cleaned["room_type"] = room_type
    if "size" in data:
        size = data["size"]
        if size is None:
            cleaned["size"] = None
        elif isinstance(size, bool) or not isinstance(size, (int, float)) or not math.isfinite(size) or size <= 0 or round(size, 2) != size:
            return None, "size must be a positive number with at most two decimal places or null"
        else:
            cleaned["size"] = size
    if "size_unit" in data:
        size_unit = data["size_unit"]
        if size_unit is not None and (
            not isinstance(size_unit, str) or size_unit not in {"sqm", "sqft"}
        ):
            return None, "size_unit must be sqm, sqft, or null"
        cleaned["size_unit"] = size_unit
    if "description" in data:
        description = data["description"]
        if description is not None and (
            not isinstance(description, str) or len(description) > 1000
        ):
            return None, "description must be text of at most 1000 characters or null"
        cleaned["description"] = description.strip() if description else None

    effective_size = cleaned.get("size")
    effective_unit = cleaned.get("size_unit")
    if effective_size is not None and not effective_unit:
        return None, "size_unit is required when size is provided"
    if "size_unit" in data and data["size_unit"] is None and effective_size is not None:
        return None, "size_unit cannot be cleared while size is set"
    return cleaned, None


@units_bp.route("/units/<int:unit_id>/rooms", methods=["GET", "POST"])
@jwt_required()
def unit_rooms(unit_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to manage rooms"}, 403
    unit = accessible_unit(user, unit_id)
    if not unit:
        return {"error": "Unit not found"}, 404

    if request.method == "GET":
        return {"rooms": [room.to_dict() for room in unit.rooms]}, 200

    if len(unit.rooms) >= 30:
        return {"error": "A unit cannot have more than 30 room records"}, 409
    cleaned, error = clean_room_data(request.get_json(silent=True))
    if error:
        return {"error": error}, 400
    if cleaned.get("size") is not None and not cleaned.get("size_unit"):
        return {"error": "size_unit is required when size is provided"}, 400
    room = Room(unit_id=unit.id, **cleaned)
    db.session.add(room)
    db.session.commit()
    return {"room": room.to_dict()}, 201


@units_bp.route("/rooms/<int:room_id>", methods=["PUT", "DELETE"])
@jwt_required()
def update_or_delete_room(room_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to manage rooms"}, 403
    room = db.session.get(Room, room_id)
    if not room or not accessible_unit(user, room.unit_id):
        return {"error": "Room not found"}, 404

    if request.method == "DELETE":
        db.session.delete(room)
        db.session.commit()
        return {"message": "Room deleted successfully"}, 200

    cleaned, error = clean_room_data(
        request.get_json(silent=True),
        partial=True,
        defaults={
            "name": room.name,
            "room_type": room.room_type,
            "size": room.size,
            "size_unit": room.size_unit,
            "description": room.description,
        },
    )
    if error:
        return {"error": error}, 400
    size = cleaned.get("size", room.size)
    size_unit = cleaned.get("size_unit", room.size_unit)
    if size is not None and not size_unit:
        return {"error": "size_unit is required when size is provided"}, 400
    for field, value in cleaned.items():
        setattr(room, field, value)
    db.session.commit()
    return {"room": room.to_dict()}, 200
