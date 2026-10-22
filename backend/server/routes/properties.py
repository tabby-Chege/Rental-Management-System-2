import math
from datetime import date
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import exists, or_

from server.extensions import db
from server.models import Property, User
from server.models_communications import PropertyConversation
from server.models_application import Application, RESERVED_APPLICATION_STATUSES
from server.models_unit_lease import Lease, Unit
from server.money import currency_precision, parse_money
from server.occupancy import property_json, property_occupancy, unit_occupancy
from server.pagination import get_pagination, pagination_metadata
from server.reservations import process_reservations
from server.unit_validation import validate_unit_data


properties_bp = Blueprint("properties", __name__, url_prefix="/api/properties")

REQUIRED_FIELDS = ["name", "address_line", "city"]
OPTIONAL_FIELDS = [
    "country", "region", "postal_code", "time_zone", "currency",
    "rental_type", "subtype", "floors", "description",
]
LEGACY_FIELDS = {
    "address": "address_line",
    "state": "region",
    "zip_code": "postal_code",
}
MAX_LENGTHS = {
    "name": 120,
    "address_line": 255,
    "city": 100,
    "country": 2,
    "region": 100,
    "postal_code": 20,
    "time_zone": 64,
    "currency": 3,
    "rental_type": 20,
    "subtype": 30,
}
RENTAL_TYPES = {"multi_unit", "whole_property"}
PROPERTY_SUBTYPES = {
    "apartment_block", "bungalow", "maisonette", "villa", "townhouse", "commercial",
}


# ---------------------------------------------------------------------------
# Ownership helpers (David can import these for the units routes)
# ---------------------------------------------------------------------------

def get_current_user():
    """Return the logged-in User, or None if the token's user no longer exists."""
    return db.session.get(User, int(get_jwt_identity()))


def owned_properties_query(user):
    """Properties this user may see.

    Managers can only see their own properties. Tenant users and public browsing
    should use the all-properties query through the optional `scope` argument.
    """
    query = Property.query

    if user.role != "admin":
        query = query.filter_by(owner_id=user.id)

    return query


def get_accessible_property(property_id, user):
    """Return the property if the user may access it, otherwise None.

    A property that belongs to someone else is treated exactly like a property
    that does not exist, so its existence is never leaked.
    """
    return owned_properties_query(user).filter_by(id=property_id).first()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def clean_payload(data, require_all):
    """Validate and normalise incoming JSON.

    Returns (cleaned_dict, error_message). Only known fields are kept, so a
    client can never set owner_id, id or created_at.
    """
    data = dict(data)
    if "reservation_hold_hours" in data:
        return None, "Reservation payments have a fixed one-hour deadline"
    legacy_address_payload = "address" in data
    for legacy_name, current_name in LEGACY_FIELDS.items():
        if legacy_name in data:
            if current_name in data:
                return None, f"Send either {legacy_name} or {current_name}, not both"
            data[current_name] = data.pop(legacy_name)

    cleaned = {}

    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        if field not in data:
            continue

        value = data[field]

        if field == "floors":
            if isinstance(value, bool) or not isinstance(value, int):
                return None, f"{field} must be a whole number"
        else:
            if value is not None and not isinstance(value, str):
                return None, f"{field} must be text"
            value = value.strip() if value else value

        if field in REQUIRED_FIELDS and not value:
            return None, f"{field} cannot be empty"

        if value and isinstance(value, str) and len(value) > MAX_LENGTHS.get(field, 10_000):
            return None, f"{field} is too long"

        cleaned[field] = (
            value
            if field == "floors"
            else (value or None)
        )

    if require_all:
        if legacy_address_payload:
            cleaned.setdefault("country", "KE")
            cleaned.setdefault("time_zone", "Africa/Nairobi")
            cleaned.setdefault("currency", "KES")
        else:
            missing_global_fields = {
                "country", "time_zone", "currency",
            } - cleaned.keys()
            if missing_global_fields:
                return None, (
                    "Missing required property fields: "
                    + ", ".join(sorted(missing_global_fields))
                )

    if "country" in cleaned and not re.fullmatch(r"[A-Z]{2}", cleaned["country"] or ""):
        return None, "country must be a two-letter uppercase country code"
    if "currency" in cleaned and currency_precision(cleaned["currency"]) is None:
        return None, "currency must be a valid ISO 4217 code"
    if "time_zone" in cleaned:
        try:
            ZoneInfo(cleaned["time_zone"])
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return None, "time_zone must be a valid IANA time zone"

    if "rental_type" in cleaned and cleaned["rental_type"] not in RENTAL_TYPES:
        return None, "rental_type must be multi_unit or whole_property"
    if "subtype" in cleaned and cleaned["subtype"] not in PROPERTY_SUBTYPES:
        return None, "subtype must be a supported property type"
    if "floors" in cleaned:
        value = cleaned["floors"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None, "floors must be a whole number of at least 1"
    if require_all:
        cleaned.setdefault("rental_type", "multi_unit")
        cleaned.setdefault("subtype", "apartment_block")
        cleaned.setdefault("floors", 1)

    if require_all:
        missing = [f for f in REQUIRED_FIELDS if f not in cleaned]
        if missing:
            return None, f"Missing required fields: {', '.join(missing)}"

    return cleaned, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@properties_bp.route("", methods=["GET"])
@jwt_required()
def list_properties():
    user = get_current_user()

    if not user:
        return {"error": "User not found"}, 404

    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400

    page, per_page = pagination
    query = owned_properties_query(user)

    search = request.args.get("q", "").strip()
    if len(search) > 120:
        return {"error": "Search query must be 120 characters or fewer"}, 400
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Property.name.ilike(pattern),
                Property.address.ilike(pattern),
                Property.city.ilike(pattern),
                Property.state.ilike(pattern),
                Property.zip_code.ilike(pattern),
            )
        )

    city = request.args.get("city", "").strip()
    if len(city) > 100:
        return {"error": "City must be 100 characters or fewer"}, 400
    if city:
        query = query.filter(Property.city.ilike(f"%{city}%"))

    result = query.order_by(Property.created_at.desc(), Property.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    summaries = property_occupancy(result.items)
    return {
        "properties": [
            property_json(prop, summaries[prop.id]) for prop in result.items
        ],
        "pagination": pagination_metadata(result),
    }, 200


@properties_bp.route("/summary", methods=["GET"])
@jwt_required()
def get_portfolio_summary():
    user = get_current_user()
    if not user:
        return {"error": "User not found"}, 404
    properties = owned_properties_query(user).all()
    summaries = property_occupancy(properties)
    totals = {
        "total_units": 0,
        "occupied_units": 0,
        "reserved_units": 0,
        "vacant_units": 0,
    }
    for summary in summaries.values():
        for field in totals:
            totals[field] += summary[field]
    return {
        "property_count": len(properties),
        "occupancy_summary": totals,
    }, 200


@properties_bp.route("/public", methods=["GET"])
def list_public_properties():
    process_reservations()
    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400

    query = Property.query
    search = request.args.get("q", "").strip()
    city = request.args.get("city", "").strip()
    if len(search) > 120:
        return {"error": "Search query must be 120 characters or fewer"}, 400
    if len(city) > 100:
        return {"error": "City must be 100 characters or fewer"}, 400
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Property.name.ilike(pattern),
                Property.address.ilike(pattern),
                Property.city.ilike(pattern),
                Property.state.ilike(pattern),
                Property.zip_code.ilike(pattern),
            )
        )
    if city:
        query = query.filter(Property.city.ilike(f"%{city}%"))

    min_rent = request.args.get("min_rent")
    max_rent = request.args.get("max_rent")
    bedrooms = request.args.get("bedrooms")
    available = request.args.get("available")
    unit_filter = Unit.query.filter(Unit.property_id == Property.id)
    try:
        if min_rent is not None:
            min_rent_value = float(min_rent)
            if not math.isfinite(min_rent_value) or min_rent_value < 0:
                raise ValueError
            unit_filter = unit_filter.filter(Unit.rent_amount >= min_rent_value)
        if max_rent is not None:
            max_rent_value = float(max_rent)
            if not math.isfinite(max_rent_value) or max_rent_value < 0:
                raise ValueError
            unit_filter = unit_filter.filter(Unit.rent_amount <= max_rent_value)
    except ValueError:
        return {"error": "Rent filters must be non-negative numbers"}, 400

    if min_rent is not None and max_rent is not None:
        if min_rent_value > max_rent_value:
            return {"error": "min_rent must not exceed max_rent"}, 400
    if bedrooms is not None:
        try:
            bedroom_count = int(bedrooms)
            if bedroom_count < 0:
                raise ValueError
        except ValueError:
            return {"error": "bedrooms must be a non-negative integer"}, 400
        unit_filter = unit_filter.filter(Unit.bedrooms == bedroom_count)
    if available is not None:
        if available.lower() not in {"true", "false"}:
            return {"error": "available must be true or false"}, 400
        if available.lower() == "true":
            approved_application = exists().where(
                Application.unit_id == Unit.id,
                Application.status.in_(RESERVED_APPLICATION_STATUSES),
            )
            unit_filter = unit_filter.filter(
                ~exists().where(
                    Lease.unit_id == Unit.id,
                    Lease.status == "active",
                    Lease.start_date <= date.today(),
                    Lease.end_date >= date.today(),
                ),
                ~approved_application,
            )
    if any(value is not None for value in (min_rent, max_rent, bedrooms, available)):
        query = query.filter(unit_filter.exists())

    page, per_page = pagination
    result = query.order_by(Property.created_at.desc(), Property.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    properties = result.items
    bedroom_counts = {prop.id: set() for prop in properties}
    if bedroom_counts:
        available_bedrooms = (
            db.session.query(Unit.property_id, Unit.bedrooms)
            .filter(
                Unit.property_id.in_(bedroom_counts),
                ~exists().where(
                    Lease.unit_id == Unit.id,
                    Lease.status == "active",
                    Lease.start_date <= date.today(),
                    Lease.end_date >= date.today(),
                ),
                ~exists().where(
                    Application.unit_id == Unit.id,
                    Application.status.in_(RESERVED_APPLICATION_STATUSES),
                ),
            )
            .distinct()
            .all()
        )
        for property_id, bedrooms in available_bedrooms:
            bedroom_counts[property_id].add(bedrooms)

    summaries = property_occupancy(properties)
    return {
        "properties": [
            {
                **property_json(prop, summaries[prop.id]),
                "available_bedroom_counts": (
                    sorted(count for count in bedroom_counts[prop.id] if count is not None)
                    + ([None] if None in bedroom_counts[prop.id] else [])
                ),
            }
            for prop in properties
        ],
        "pagination": pagination_metadata(result),
    }, 200


@properties_bp.route("/public/<int:property_id>", methods=["GET"])
def get_public_property(property_id):
    prop = db.session.get(Property, property_id)
    if not prop:
        return {"error": "Property not found"}, 404
    summary = property_occupancy([prop])[prop.id]
    return {"property": property_json(prop, summary)}, 200


@properties_bp.route("/public/<int:property_id>/units", methods=["GET"])
def list_public_property_units(property_id):
    prop = db.session.get(Property, property_id)
    if not prop:
        return {"error": "Property not found"}, 404

    raw_unit_id = request.args.get("unit_id")
    if raw_unit_id is not None:
        if not raw_unit_id.isdecimal() or int(raw_unit_id) < 1:
            return {"error": "unit_id must be a positive integer"}, 400

    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    units_query = Unit.query.filter_by(property_id=property_id)
    if raw_unit_id is not None:
        units_query = units_query.filter(Unit.id == int(raw_unit_id))
    result = units_query.order_by(Unit.unit_number, Unit.id).paginate(
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


@properties_bp.route("", methods=["POST"])
@jwt_required()
def create_property():
    user = get_current_user()

    if not user:
        return {"error": "User not found"}, 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400

    whole_unit_data = data.pop("whole_unit", None)
    cleaned, error = clean_payload(data, require_all=True)

    if error:
        return {"error": error}, 400

    rental_type = cleaned["rental_type"]
    if rental_type == "whole_property":
        if not isinstance(whole_unit_data, dict):
            return {"error": "whole_unit details are required for a whole property"}, 400
        unit_fields = set(whole_unit_data)
        missing = {"bedrooms", "bathrooms", "rent_amount"} - unit_fields
        if missing:
            return {
                "error": "Missing required whole_unit fields: " + ", ".join(sorted(missing))
            }, 400
        if "unit_number" in unit_fields:
            return {"error": "whole_unit unit_number is assigned automatically"}, 400
        unit_data, unit_error = validate_unit_data(
            whole_unit_data,
            currency=cleaned["currency"],
            floors=cleaned["floors"],
            defaults={"unit_number": "Entire property", "floor_number": 1},
        )
        if unit_error:
            return {"error": f"whole_unit: {unit_error}"}, 400
    elif whole_unit_data is not None:
        return {"error": "whole_unit is only valid for whole_property rentals"}, 400

    # The owner is always the logged-in user, never taken from the request.
    prop = Property(owner_id=user.id, **cleaned)

    db.session.add(prop)
    if rental_type == "whole_property":
        db.session.flush()
        db.session.add(Unit(property_id=prop.id, **unit_data))
    db.session.commit()

    return {
        "message": "Property created successfully",
        "property": property_json(prop, property_occupancy([prop])[prop.id]),
    }, 201


@properties_bp.route("/<int:property_id>", methods=["GET"])
@jwt_required()
def get_property(property_id):
    user = get_current_user()

    if not user:
        return {"error": "User not found"}, 404

    prop = get_accessible_property(property_id, user)

    if not prop:
        return {"error": "Property not found"}, 404

    summary = property_occupancy([prop])[prop.id]
    return {"property": property_json(prop, summary)}, 200


@properties_bp.route("/<int:property_id>", methods=["PUT"])
@jwt_required()
def update_property(property_id):
    user = get_current_user()

    if not user:
        return {"error": "User not found"}, 404

    prop = get_accessible_property(property_id, user)

    if not prop:
        return {"error": "Property not found"}, 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400

    whole_unit_data = data.pop("whole_unit", None)
    cleaned, error = clean_payload(data, require_all=False)

    if error:
        return {"error": error}, 400

    changing_to_whole = (
        cleaned.get("rental_type") == "whole_property"
        and prop.rental_type != "whole_property"
    )
    if "rental_type" in cleaned and cleaned["rental_type"] != prop.rental_type:
        if Unit.query.filter_by(property_id=prop.id).first():
            return {
                "error": "Rental type cannot change after units have been created"
            }, 409
        if cleaned["rental_type"] != "whole_property":
            return {"error": "A whole property cannot be changed to multi-unit"}, 409
        if not isinstance(whole_unit_data, dict):
            return {"error": "whole_unit details are required when changing to a whole property"}, 400
        missing = {"bedrooms", "bathrooms", "rent_amount"} - whole_unit_data.keys()
        if missing:
            return {
                "error": "Missing required whole_unit fields: " + ", ".join(sorted(missing))
            }, 400
        if "unit_number" in whole_unit_data:
            return {"error": "whole_unit unit_number is assigned automatically"}, 400
        unit_data, unit_error = validate_unit_data(
            whole_unit_data,
            currency=cleaned.get("currency", prop.currency),
            floors=cleaned.get("floors", prop.floors),
            defaults={"unit_number": "Entire property", "floor_number": 1},
        )
        if unit_error:
            return {"error": f"whole_unit: {unit_error}"}, 400
    elif whole_unit_data is not None and prop.rental_type != "whole_property":
        return {"error": "whole_unit details are only valid for whole properties"}, 400
    elif whole_unit_data is not None:
        if "unit_number" in whole_unit_data:
            return {"error": "whole_unit unit_number cannot be changed"}, 400
        whole_unit = Unit.query.filter_by(property_id=prop.id).first()
        if not whole_unit:
            return {"error": "The whole property is missing its required unit"}, 409
        unit_data, unit_error = validate_unit_data(
            whole_unit_data,
            defaults={
                "unit_number": "Entire property",
                "unit_type": whole_unit.unit_type,
                "bedrooms": whole_unit.bedrooms,
                "bathrooms": whole_unit.bathrooms,
                "rent_amount": whole_unit.rent_amount,
                "floor_number": whole_unit.floor_number,
                "layout": whole_unit.layout,
                "size": whole_unit.size,
                "size_unit": whole_unit.size_unit,
                "furnished": whole_unit.furnished,
                "description": whole_unit.description,
            },
            currency=cleaned.get("currency", prop.currency),
            floors=cleaned.get("floors", prop.floors),
            partial=True,
        )
        if unit_error:
            return {"error": f"whole_unit: {unit_error}"}, 400
    new_floors = cleaned.get("floors", prop.floors)
    if Unit.query.filter(
        Unit.property_id == prop.id,
        Unit.floor_number > new_floors,
    ).first():
        return {
            "error": "The number of floors cannot be lower than a unit's floor number"
        }, 409

    new_currency = cleaned.get("currency")
    if new_currency and new_currency != prop.currency:
        if (
            Lease.query.join(Unit, Lease.unit_id == Unit.id)
            .filter(Unit.property_id == prop.id)
            .first()
        ):
            return {"error": "A property's currency cannot change after it has a lease"}, 409
        for unit in Unit.query.filter_by(property_id=prop.id).all():
            if unit.rent_amount is not None:
                _, amount_error = parse_money(unit.rent_amount, new_currency)
                if amount_error:
                    return {
                        "error": "Existing unit rents must match the new currency's decimal precision"
                    }, 409

    for field, value in cleaned.items():
        setattr(prop, field, value)
    if changing_to_whole:
        db.session.add(Unit(property=prop, **unit_data))
    elif whole_unit_data is not None:
        for field, value in unit_data.items():
            setattr(whole_unit, field, value)

    db.session.commit()

    return {
        "message": "Property updated successfully",
        "property": property_json(prop, property_occupancy([prop])[prop.id]),
    }, 200


@properties_bp.route("/<int:property_id>", methods=["DELETE"])
@jwt_required()
def delete_property(property_id):
    user = get_current_user()

    if not user:
        return {"error": "User not found"}, 404

    prop = get_accessible_property(property_id, user)

    if not prop:
        return {"error": "Property not found"}, 404

    if Unit.query.filter_by(property_id=prop.id).first():
        return {
            "error": "Delete or move this property's units before deleting the property"
        }, 409
    if PropertyConversation.query.filter_by(property_id=prop.id).first():
        return {
            "error": "This property has message history and cannot be deleted"
        }, 409

    db.session.delete(prop)
    db.session.commit()

    return {"message": "Property deleted successfully"}, 200
