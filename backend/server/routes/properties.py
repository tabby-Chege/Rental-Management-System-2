from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import or_

from server.extensions import db
from server.models import Property, User
from server.models_unit_lease import Unit
from server.pagination import get_pagination, pagination_metadata


properties_bp = Blueprint("properties", __name__, url_prefix="/api/properties")

REQUIRED_FIELDS = ["name", "address", "city", "state"]
OPTIONAL_FIELDS = ["zip_code", "description"]
MAX_LENGTHS = {
    "name": 120,
    "address": 255,
    "city": 100,
    "state": 100,
    "zip_code": 20,
}


# ---------------------------------------------------------------------------
# Ownership helpers (David can import these for the units routes)
# ---------------------------------------------------------------------------

def get_current_user():
    """Return the logged-in User, or None if the token's user no longer exists."""
    return db.session.get(User, int(get_jwt_identity()))


def owned_properties_query(user):
    """Properties this user may see: all for admins, only their own otherwise."""
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
    cleaned = {}

    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        if field not in data:
            continue

        value = data[field]

        if value is not None and not isinstance(value, str):
            return None, f"{field} must be text"

        value = value.strip() if value else value

        if field in REQUIRED_FIELDS and not value:
            return None, f"{field} cannot be empty"

        if value and len(value) > MAX_LENGTHS.get(field, 10_000):
            return None, f"{field} is too long"

        cleaned[field] = value or None

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

    return {
        "properties": [prop.to_dict() for prop in result.items],
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

    cleaned, error = clean_payload(data, require_all=True)

    if error:
        return {"error": error}, 400

    # The owner is always the logged-in user, never taken from the request.
    prop = Property(owner_id=user.id, **cleaned)

    db.session.add(prop)
    db.session.commit()

    return {
        "message": "Property created successfully",
        "property": prop.to_dict(),
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

    return {"property": prop.to_dict()}, 200


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

    cleaned, error = clean_payload(data, require_all=False)

    if error:
        return {"error": error}, 400

    for field, value in cleaned.items():
        setattr(prop, field, value)

    db.session.commit()

    return {
        "message": "Property updated successfully",
        "property": prop.to_dict(),
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

    db.session.delete(prop)
    db.session.commit()

    return {"message": "Property deleted successfully"}, 200
