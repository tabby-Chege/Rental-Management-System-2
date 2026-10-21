from io import BytesIO
from pathlib import Path
import uuid

from flask import Blueprint, current_app, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import and_, exists, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from server.extensions import db
from server.models import Property, User
from server.models_media import ListingReport, PropertyPhoto
from server.models_unit_lease import Room, Unit
from server.photo_validation import InvalidPropertyPhoto, normalize_property_photo
from server.storage import (
    ObjectStorageError,
    delete_private_object,
    get_private_object,
    put_private_object,
)


media_bp = Blueprint("media", __name__, url_prefix="/api")
MANAGER_ROLES = {"landlord", "admin"}
REPORT_REASONS = {
    "inaccurate",
    "scam",
    "unavailable",
    "inappropriate",
    "other",
}
MAX_PHOTOS_PER_LISTING = 30
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def current_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    return db.session.get(User, user_id)


def owned_property(user, property_id):
    query = Property.query.filter_by(id=property_id)
    if user.role != "admin":
        query = query.filter_by(owner_id=user.id)
    return query.first()


def owned_unit(user, unit_id):
    query = Unit.query.join(Property, Unit.property_id == Property.id).filter(
        Unit.id == unit_id
    )
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query.first()


def _listing_photos(property_id=None, unit_id=None):
    query = PropertyPhoto.query
    if property_id is not None:
        query = query.filter_by(property_id=property_id)
    else:
        query = query.filter_by(unit_id=unit_id)
    return query.order_by(PropertyPhoto.is_cover.desc(), PropertyPhoto.id).all()


def _upload_photo(user, property_id=None, unit_id=None):
    if user.role not in MANAGER_ROLES:
        return {"error": "Only property managers can upload listing photos"}, 403
    listing = (
        owned_property(user, property_id)
        if property_id is not None
        else owned_unit(user, unit_id)
    )
    if not listing:
        return {"error": "Listing not found"}, 404

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return {"error": "An image file is required"}, 400
    if Path(uploaded.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        return {"error": "Only JPG, PNG, and WebP images are supported"}, 400

    room_id = request.form.get("room_id")
    room = None
    if room_id:
        if unit_id is None or not room_id.isdecimal() or int(room_id) < 1:
            return {"error": "room_id must identify a room in the selected unit"}, 400
        room = Room.query.filter_by(id=int(room_id), unit_id=unit_id).first()
        if not room:
            return {"error": "Room not found for this unit"}, 404

    cover_value = request.form.get("is_cover", "").lower()
    if cover_value not in {"", "true", "false", "1", "0"}:
        return {"error": "is_cover must be true or false"}, 400
    photos = _listing_photos(property_id=property_id, unit_id=unit_id)
    if len(photos) >= MAX_PHOTOS_PER_LISTING:
        return {"error": f"A listing can have at most {MAX_PHOTOS_PER_LISTING} photos"}, 409

    max_bytes = current_app.config["PROPERTY_PHOTO_MAX_BYTES"]
    try:
        contents = uploaded.stream.read(max_bytes + 1)
        normalized, content_type = normalize_property_photo(contents, max_bytes)
    except InvalidPropertyPhoto as validation_error:
        return {"error": str(validation_error)}, 400

    is_cover = cover_value in {"true", "1"} or not any(
        photo.is_cover for photo in photos
    )
    object_key = uuid.uuid4().hex
    try:
        put_private_object(object_key, normalized, content_type)
    except ObjectStorageError:
        current_app.logger.exception("Property photo upload failed")
        return {"error": "Photo storage is unavailable"}, 503

    try:
        if is_cover:
            for photo in photos:
                photo.is_cover = False
            db.session.flush()
        photo = PropertyPhoto(
            property_id=property_id,
            unit_id=unit_id,
            room_id=room.id if room else None,
            object_key=object_key,
            content_type=content_type,
            file_size=len(normalized),
            is_cover=is_cover,
        )
        db.session.add(photo)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        _remove_orphaned_object(object_key)
        return {"error": "Could not assign this photo as the listing cover"}, 409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not save property photo metadata")
        _remove_orphaned_object(object_key)
        return {"error": "Could not save photo metadata"}, 500
    return {"photo": photo.to_dict()}, 201


def _remove_orphaned_object(object_key):
    try:
        delete_private_object(object_key)
    except ObjectStorageError:
        current_app.logger.exception("Could not remove orphaned property photo")


def _accessible_photo(user, photo_id):
    query = PropertyPhoto.query.filter_by(id=photo_id)
    if user.role != "admin":
        property_owned = exists().where(
            and_(
                Property.id == PropertyPhoto.property_id,
                Property.owner_id == user.id,
            )
        )
        unit_owned = exists().where(
            and_(
                Unit.id == PropertyPhoto.unit_id,
                Unit.property_id == Property.id,
                Property.owner_id == user.id,
            )
        )
        query = query.filter(or_(property_owned, unit_owned))
    return query.first()


@media_bp.route("/properties/<int:property_id>/photos", methods=["POST"])
@jwt_required()
def upload_property_photo(property_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    return _upload_photo(user, property_id=property_id)


@media_bp.route("/units/<int:unit_id>/photos", methods=["POST"])
@jwt_required()
def upload_unit_photo(unit_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    return _upload_photo(user, unit_id=unit_id)


@media_bp.route("/public/photos/<int:photo_id>", methods=["GET"])
def get_public_photo(photo_id):
    photo = db.session.get(PropertyPhoto, photo_id)
    if not photo:
        return {"error": "Photo not found"}, 404
    try:
        contents = get_private_object(photo.object_key)
    except ObjectStorageError:
        current_app.logger.exception("Public property photo retrieval failed")
        return {"error": "Photo storage is unavailable"}, 503
    response = send_file(
        BytesIO(contents),
        mimetype=photo.content_type,
        conditional=True,
        max_age=3600,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@media_bp.route("/photos/<int:photo_id>/cover", methods=["PATCH"])
@jwt_required()
def set_photo_cover(photo_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only property managers can update listing photos"}, 403
    photo = _accessible_photo(user, photo_id)
    if not photo:
        return {"error": "Photo not found"}, 404
    photos = _listing_photos(
        property_id=photo.property_id, unit_id=photo.unit_id
    )
    for other_photo in photos:
        if other_photo.id != photo.id:
            other_photo.is_cover = False
    db.session.flush()
    photo.is_cover = True
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "Could not set the listing cover"}, 409
    return {"photo": photo.to_dict()}, 200


@media_bp.route("/photos/<int:photo_id>", methods=["DELETE"])
@jwt_required()
def delete_photo(photo_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only property managers can delete listing photos"}, 403
    photo = _accessible_photo(user, photo_id)
    if not photo:
        return {"error": "Photo not found"}, 404
    try:
        delete_private_object(photo.object_key)
    except ObjectStorageError:
        current_app.logger.exception("Property photo delete failed")
        return {"error": "Photo storage is unavailable"}, 503
    photos = _listing_photos(property_id=photo.property_id, unit_id=photo.unit_id)
    was_cover = photo.is_cover
    if was_cover:
        photo.is_cover = False
        db.session.flush()
    replacement = None
    if was_cover:
        replacement = next((item for item in photos if item.id != photo.id), None)
        if replacement:
            replacement.is_cover = True
    db.session.delete(photo)
    db.session.commit()
    return {"message": "Photo deleted"}, 200


@media_bp.route("/listing-reports", methods=["POST"])
@jwt_required()
def create_listing_report():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be a JSON object"}, 400

    property_id = data.get("property_id")
    unit_id = data.get("unit_id")
    if (property_id is None) == (unit_id is None):
        return {"error": "Report either a property or a unit"}, 400
    if property_id is not None:
        if isinstance(property_id, bool) or not isinstance(property_id, int) or property_id < 1:
            return {"error": "property_id must be a positive integer"}, 400
        listing = db.session.get(Property, property_id)
        if not listing:
            return {"error": "Listing not found"}, 404
        report_property_id, report_unit_id = listing.id, None
        owner_id = listing.owner_id
    else:
        if isinstance(unit_id, bool) or not isinstance(unit_id, int) or unit_id < 1:
            return {"error": "unit_id must be a positive integer"}, 400
        listing = db.session.get(Unit, unit_id)
        if not listing:
            return {"error": "Listing not found"}, 404
        report_property_id, report_unit_id = None, listing.id
        owner_id = listing.property.owner_id
    if owner_id == user.id and user.role != "admin":
        return {"error": "You cannot report your own listing"}, 409

    reason = data.get("reason")
    details = data.get("details", "")
    if not isinstance(reason, str) or reason not in REPORT_REASONS:
        return {"error": "Select a supported report reason"}, 400
    if not isinstance(details, str) or len(details.strip()) > 1000:
        return {"error": "details must be 1000 characters or fewer"}, 400

    report = ListingReport(
        user_id=user.id,
        property_id=report_property_id,
        unit_id=report_unit_id,
        reason=reason,
        details=details.strip() or None,
    )
    db.session.add(report)
    db.session.commit()
    return {"report": report.to_dict()}, 201
