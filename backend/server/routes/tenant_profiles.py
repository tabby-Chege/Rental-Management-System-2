import hashlib
import re
import uuid
from io import BytesIO

from flask import Blueprint, current_app, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from server.document_validation import InvalidTenantDocument, normalize_tenant_document
from server.extensions import db
from server.models import Property, User
from server.models_application import Application
from server.models_tenant import TenantDocument, TenantProfile
from server.models_unit_lease import Unit
from server.storage import (
    ObjectStorageError,
    delete_private_object,
    get_private_object,
    put_private_object,
)
from server.tenant_security import (
    TenantDataProtectionError,
    decrypt_id_number,
    encrypt_id_number,
)

tenant_profiles_bp = Blueprint("tenant_profiles", __name__, url_prefix="/api")
MANAGER_ROLES = {"landlord", "admin"}
PROFILE_FIELDS = {
    "full_name",
    "phone",
    "employment_status",
    "employer",
    "job_title",
    "emergency_contact_name",
    "emergency_contact_phone",
    "emergency_contact_relationship",
    "id_type",
    "id_number",
    "previous_landlord_name",
    "previous_landlord_contact",
}
REQUIRED_PROFILE_FIELDS = {
    "full_name",
    "phone",
    "employment_status",
    "emergency_contact_name",
    "emergency_contact_phone",
    "emergency_contact_relationship",
}
DOCUMENT_KINDS = {"identity", "income", "reference"}
PHONE_PATTERN = re.compile(r"\+[1-9]\d{6,14}")


def current_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    return db.session.get(User, user_id)


def error(message, status):
    return {"error": message}, status


def require_tenant():
    user = current_user()
    if not user:
        return None, error("User not found", 404)
    if user.role != "tenant":
        return None, error("Only tenants can manage tenant profiles", 403)
    return user, None


def profile_documents(user_id):
    return (
        TenantDocument.query.filter_by(user_id=user_id)
        .order_by(TenantDocument.uploaded_at.desc(), TenantDocument.id.desc())
        .all()
    )


def profile_json(profile, documents):
    try:
        id_number = decrypt_id_number(profile.encrypted_id_number)
    except TenantDataProtectionError:
        current_app.logger.exception(
            "Unable to decrypt tenant ID details for profile %s", profile.id
        )
        return None, error("Tenant ID details are unavailable", 503)
    return {
        "profile": profile.to_dict(id_number=id_number),
        "documents": [document.to_dict() for document in documents],
    }, None


def clean_phone(value, label):
    if not isinstance(value, str):
        return None, f"{label} must use international E.164 format"
    phone = value.strip()
    if not PHONE_PATTERN.fullmatch(phone):
        return None, f"{label} must use international E.164 format"
    return phone, None


def validate_profile_data(data, existing):
    if not isinstance(data, dict) or not data:
        return None, "Request body must be a JSON object with profile fields"
    unknown = set(data) - PROFILE_FIELDS
    if unknown:
        return None, "Unsupported fields: " + ", ".join(sorted(unknown))

    values = {}
    for field in PROFILE_FIELDS & data.keys():
        value = data[field]
        if field in {"phone", "emergency_contact_phone"}:
            value, problem = clean_phone(value, field.replace("_", " ").title())
            if problem:
                return None, problem
        elif field == "id_number":
            if value is not None and not isinstance(value, str):
                return None, "ID number must be text"
            value = value.strip() if value else None
            if value and len(value) > 120:
                return None, "ID number is too long"
        elif value is not None:
            if not isinstance(value, str):
                return None, f"{field.replace('_', ' ').title()} must be text"
            value = value.strip()
        values[field] = value

    limits = {
        "full_name": 120,
        "employment_status": 40,
        "employer": 120,
        "job_title": 120,
        "emergency_contact_name": 120,
        "emergency_contact_relationship": 80,
        "id_type": 40,
        "previous_landlord_name": 120,
        "previous_landlord_contact": 120,
    }
    for field, limit in limits.items():
        value = values.get(field, getattr(existing, field, None) if existing else None)
        if value is not None and len(value) > limit:
            return None, f"{field.replace('_', ' ').title()} must be {limit} characters or fewer"

    for field in REQUIRED_PROFILE_FIELDS:
        value = values.get(field, getattr(existing, field, None) if existing else None)
        if not isinstance(value, str) or not value:
            return None, f"{field.replace('_', ' ').title()} is required"

    if values.get("id_number") and not values.get(
        "id_type", getattr(existing, "id_type", None) if existing else None
    ):
        return None, "ID type is required when an ID number is provided"

    return values, None


@tenant_profiles_bp.route("/tenant-profile/me", methods=["GET"])
@jwt_required()
def get_my_profile():
    user, response = require_tenant()
    if response:
        return response

    profile = TenantProfile.query.filter_by(user_id=user.id).first()
    if not profile:
        return {"profile": None, "documents": []}, 200
    payload, profile_error = profile_json(profile, profile_documents(user.id))
    if profile_error:
        return profile_error
    return payload, 200


@tenant_profiles_bp.route("/tenant-profile/me", methods=["PUT"])
@jwt_required()
def update_my_profile():
    user, response = require_tenant()
    if response:
        return response

    profile = TenantProfile.query.filter_by(user_id=user.id).first()
    values, problem = validate_profile_data(request.get_json(silent=True), profile)
    if problem:
        return error(problem, 400)

    encrypted_id_number = None
    has_id_number_update = "id_number" in values
    if has_id_number_update:
        try:
            encrypted_id_number = encrypt_id_number(values.pop("id_number"))
        except TenantDataProtectionError as protection_error:
            return error(str(protection_error), 503)

    if not profile:
        profile = TenantProfile(
            user_id=user.id,
            full_name=user.name,
            phone="",
            employment_status="",
            emergency_contact_name="",
            emergency_contact_phone="",
            emergency_contact_relationship="",
        )
        db.session.add(profile)

    if has_id_number_update:
        profile.encrypted_id_number = encrypted_id_number

    for field, value in values.items():
        setattr(profile, field, value)

    db.session.commit()
    payload, profile_error = profile_json(profile, profile_documents(user.id))
    if profile_error:
        return profile_error
    return payload, 200


@tenant_profiles_bp.route("/tenant-profile/me/documents", methods=["POST"])
@jwt_required()
def upload_my_document():
    user, response = require_tenant()
    if response:
        return response
    if not TenantProfile.query.filter_by(user_id=user.id).first():
        return error("Complete your tenant profile before uploading documents", 409)

    uploaded = request.files.get("file")
    kind = request.form.get("kind", "identity")
    if not uploaded or not uploaded.filename:
        return error("A document file is required", 400)
    if kind not in DOCUMENT_KINDS:
        return error("kind must be identity, income, or reference", 400)

    max_bytes = current_app.config["TENANT_DOCUMENT_MAX_BYTES"]
    contents = uploaded.stream.read(max_bytes + 1)
    try:
        normalized, content_type = normalize_tenant_document(contents, max_bytes)
    except InvalidTenantDocument as validation_error:
        return error(str(validation_error), 400)

    object_key = uuid.uuid4().hex
    try:
        put_private_object(object_key, normalized, content_type)
    except ObjectStorageError:
        current_app.logger.exception("Tenant document upload failed")
        return error("Private document storage is unavailable", 503)

    document = TenantDocument(
        user_id=user.id,
        kind=kind,
        object_key=object_key,
        content_type=content_type,
        file_size=len(normalized),
        sha256=hashlib.sha256(normalized).hexdigest(),
    )
    db.session.add(document)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not record uploaded tenant document")
        try:
            delete_private_object(object_key)
        except ObjectStorageError:
            current_app.logger.exception("Could not remove orphaned tenant document")
        return error("Could not save document metadata", 500)
    return {"document": document.to_dict()}, 201


def application_references_document(user, document):
    query = (
        Application.query.join(Unit)
        .join(Property)
        .filter(Application.applicant_user_id == document.user_id)
    )
    if user.role not in MANAGER_ROLES:
        return False
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    for application in query.all():
        document_ids = application.profile_snapshot.get("document_ids", [])
        if document.id in document_ids:
            return True
    return False


def document_is_referenced(document):
    for application in Application.query.filter_by(
        applicant_user_id=document.user_id
    ).all():
        if document.id in application.profile_snapshot.get("document_ids", []):
            return True
    return False


def visible_document(user, document):
    if not document:
        return False
    if user.role == "tenant":
        return document.user_id == user.id
    return application_references_document(user, document)


@tenant_profiles_bp.route("/tenant-documents/<int:document_id>", methods=["GET"])
@jwt_required()
def download_document(document_id):
    user = current_user()
    if not user:
        return error("User not found", 404)
    document = db.session.get(TenantDocument, document_id)
    if not visible_document(user, document):
        return error("Document not found", 404)

    try:
        contents = get_private_object(document.object_key)
    except ObjectStorageError:
        current_app.logger.exception(
            "Tenant document download failed for document %s", document.id
        )
        return error("Private document storage is unavailable", 503)

    response = send_file(
        BytesIO(contents),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"tenant-document-{document.id}",
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@tenant_profiles_bp.route(
    "/tenant-profile/me/documents/<int:document_id>", methods=["DELETE"]
)
@jwt_required()
def delete_my_document(document_id):
    user, response = require_tenant()
    if response:
        return response
    document = TenantDocument.query.filter_by(
        id=document_id, user_id=user.id
    ).first()
    if not document:
        return error("Document not found", 404)
    if document_is_referenced(document):
        return error(
            "Documents included in an application cannot be removed", 409
        )

    try:
        delete_private_object(document.object_key)
    except ObjectStorageError:
        current_app.logger.exception(
            "Tenant document delete failed for document %s", document.id
        )
        return error("Private document storage is unavailable", 503)
    db.session.delete(document)
    db.session.commit()
    return {"message": "Document deleted"}, 200
