import hashlib
import re
import uuid
from datetime import date
from io import BytesIO

from flask import Blueprint, current_app, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from server.document_validation import InvalidTenantDocument, normalize_tenant_document
from server.extensions import db
from server.models import Payment, Property, User
from server.models_landlord_tools import LeaseDocument, MaintenancePhoto, MaintenanceRequest
from server.models_payment import RentInvoice
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit
from server.occupancy import property_occupancy
from server.pagination import get_pagination, pagination_metadata
from server.storage import (
    ObjectStorageError,
    delete_private_object,
    get_private_object,
    put_private_object,
)

landlord_tools_bp = Blueprint("landlord_tools", __name__, url_prefix="/api")
MANAGER_ROLES = {"landlord", "admin"}
MAINTENANCE_STATUSES = {"submitted", "in_progress", "resolved", "closed"}
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
MAX_MAINTENANCE_PHOTOS = 10


def current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def lease_for_user(user, lease_id):
    lease = db.session.get(Lease, lease_id)
    if not lease:
        return None
    unit = db.session.get(Unit, lease.unit_id)
    property_record = db.session.get(Property, unit.property_id) if unit else None
    if not property_record:
        return None
    if user.role == "admin":
        return lease
    if user.role == "landlord" and property_record.owner_id == user.id:
        return lease
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        if tenant and tenant.id == lease.tenant_id:
            return lease
    return None


def maintenance_payload(item):
    lease = db.session.get(Lease, item.lease_id)
    unit = db.session.get(Unit, lease.unit_id) if lease else None
    prop = db.session.get(Property, unit.property_id) if unit else None
    photos = MaintenancePhoto.query.filter_by(request_id=item.id).order_by(
        MaintenancePhoto.id
    ).all()
    return item.to_dict(
        photos=photos,
        property_name=prop.name if prop else None,
        unit_number=unit.unit_number if unit else None,
    )


def visible_maintenance(user, request_id):
    item = db.session.get(MaintenanceRequest, request_id)
    if not item:
        return None
    return item if lease_for_user(user, item.lease_id) else None


def queue_object_upload(contents, content_type):
    key = uuid.uuid4().hex
    try:
        put_private_object(key, contents, content_type)
    except ObjectStorageError:
        current_app.logger.exception("Private landlord-tool file upload failed")
        return None, ({"error": "Private file storage is unavailable"}, 503)
    return key, None


def cleanup_object(key):
    try:
        delete_private_object(key)
    except ObjectStorageError:
        current_app.logger.exception("Could not remove orphaned private file")


@landlord_tools_bp.route("/maintenance", methods=["GET"])
@jwt_required()
def list_maintenance_requests():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    query = (
        MaintenanceRequest.query.join(Lease)
        .join(Unit)
        .join(Property)
    )
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        query = query.filter(Lease.tenant_id == tenant.id) if tenant else query.filter(False)
    elif user.role == "landlord":
        query = query.filter(Property.owner_id == user.id)
    elif user.role != "admin":
        return {"error": "Only tenants and landlords can view maintenance requests"}, 403
    status = request.args.get("status")
    if status:
        if status not in MAINTENANCE_STATUSES:
            return {"error": "Invalid maintenance status"}, 400
        query = query.filter(MaintenanceRequest.status == status)
    pagination, problem = get_pagination()
    if problem:
        return {"error": problem}, 400
    page, per_page = pagination
    result = query.order_by(
        MaintenanceRequest.updated_at.desc(), MaintenanceRequest.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return {
        "requests": [maintenance_payload(item) for item in result.items],
        "pagination": pagination_metadata(result),
    }, 200


@landlord_tools_bp.route("/maintenance", methods=["POST"])
@jwt_required()
def create_maintenance_request():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role != "tenant":
        return {"error": "Only tenants can submit maintenance requests"}, 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"lease_id", "title", "description"}:
        return {"error": "Request body must contain lease_id, title, and description"}, 400
    lease_id = data.get("lease_id")
    if isinstance(lease_id, bool) or not isinstance(lease_id, int) or lease_id < 1:
        return {"error": "lease_id must be a positive integer"}, 400
    lease = lease_for_user(user, lease_id)
    if (
        not lease
        or lease.status != "active"
        or lease.start_date > date.today()
        or lease.end_date < date.today()
    ):
        return {"error": "An active lease linked to your account is required"}, 404
    title, description = data.get("title"), data.get("description")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
        return {"error": "title must contain 1 to 160 characters"}, 400
    if not isinstance(description, str) or not description.strip() or len(description.strip()) > 5000:
        return {"error": "description must contain 1 to 5000 characters"}, 400
    item = MaintenanceRequest(
        lease_id=lease.id,
        created_by_user_id=user.id,
        title=title.strip(),
        description=description.strip(),
    )
    db.session.add(item)
    db.session.commit()
    return {"request": maintenance_payload(item)}, 201


@landlord_tools_bp.route("/maintenance/<int:request_id>", methods=["PATCH"])
@jwt_required()
def update_maintenance_request(request_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords can update maintenance status"}, 403
    item = visible_maintenance(user, request_id)
    if not item:
        return {"error": "Maintenance request not found"}, 404
    if MaintenancePhoto.query.filter_by(request_id=item.id).count() >= MAX_MAINTENANCE_PHOTOS:
        return {"error": f"A maintenance request can have at most {MAX_MAINTENANCE_PHOTOS} photos"}, 409
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"status"}:
        return {"error": "Request body must contain only status"}, 400
    if data["status"] not in MAINTENANCE_STATUSES:
        return {"error": "Invalid maintenance status"}, 400
    item.status = data["status"]
    db.session.commit()
    return {"request": maintenance_payload(item)}, 200


@landlord_tools_bp.route("/maintenance/<int:request_id>/photos", methods=["POST"])
@jwt_required()
def upload_maintenance_photo(request_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    item = visible_maintenance(user, request_id)
    if not item:
        return {"error": "Maintenance request not found"}, 404
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return {"error": "A photo file is required"}, 400
    max_bytes = current_app.config["PROPERTY_PHOTO_MAX_BYTES"]
    contents = uploaded.stream.read(max_bytes + 1)
    try:
        normalized, content_type = normalize_tenant_document(contents, max_bytes)
    except InvalidTenantDocument as validation_error:
        return {"error": str(validation_error)}, 400
    if not content_type.startswith("image/"):
        return {"error": "Maintenance attachments must be JPEG, PNG, or WebP images"}, 400
    key, problem = queue_object_upload(normalized, content_type)
    if problem:
        return problem
    photo = MaintenancePhoto(
        request_id=item.id,
        object_key=key,
        content_type=content_type,
        file_size=len(normalized),
        sha256=hashlib.sha256(normalized).hexdigest(),
    )
    db.session.add(photo)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not save maintenance photo metadata")
        cleanup_object(key)
        return {"error": "Could not save maintenance photo metadata"}, 500
    return {"photo": photo.to_dict()}, 201


@landlord_tools_bp.route("/maintenance/photos/<int:photo_id>", methods=["GET"])
@jwt_required()
def download_maintenance_photo(photo_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    photo = db.session.get(MaintenancePhoto, photo_id)
    item = visible_maintenance(user, photo.request_id) if photo else None
    if not photo or not item:
        return {"error": "Maintenance photo not found"}, 404
    try:
        contents = get_private_object(photo.object_key)
    except ObjectStorageError:
        current_app.logger.exception("Maintenance photo download failed")
        return {"error": "Private file storage is unavailable"}, 503
    response = send_file(
        BytesIO(contents),
        mimetype=photo.content_type,
        as_attachment=True,
        download_name=f"maintenance-{photo.id}",
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@landlord_tools_bp.route("/leases/<int:lease_id>/documents", methods=["GET", "POST"])
@jwt_required()
def lease_documents(lease_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    lease = lease_for_user(user, lease_id)
    if not lease:
        return {"error": "Lease not found"}, 404
    if request.method == "GET":
        docs = LeaseDocument.query.filter_by(lease_id=lease.id).order_by(
            LeaseDocument.uploaded_at.desc(), LeaseDocument.id.desc()
        ).all()
        return {"documents": [document.to_dict() for document in docs]}, 200
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return {"error": "A lease document file is required"}, 400
    max_bytes = current_app.config["TENANT_DOCUMENT_MAX_BYTES"]
    contents = uploaded.stream.read(max_bytes + 1)
    try:
        normalized, content_type = normalize_tenant_document(contents, max_bytes)
    except InvalidTenantDocument as validation_error:
        return {"error": str(validation_error)}, 400
    original_filename = secure_filename(uploaded.filename) or "lease-document"
    filename = SAFE_FILENAME.sub("", original_filename)[:180] or "lease-document"
    key, problem = queue_object_upload(normalized, content_type)
    if problem:
        return problem
    document = LeaseDocument(
        lease_id=lease.id,
        uploaded_by_user_id=user.id,
        filename=filename,
        object_key=key,
        content_type=content_type,
        file_size=len(normalized),
        sha256=hashlib.sha256(normalized).hexdigest(),
    )
    db.session.add(document)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not save lease-document metadata")
        cleanup_object(key)
        return {"error": "Could not save lease-document metadata"}, 500
    return {"document": document.to_dict()}, 201


@landlord_tools_bp.route("/lease-documents/<int:document_id>", methods=["GET"])
@jwt_required()
def download_lease_document(document_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    document = db.session.get(LeaseDocument, document_id)
    if not document or not lease_for_user(user, document.lease_id):
        return {"error": "Lease document not found"}, 404
    try:
        contents = get_private_object(document.object_key)
    except ObjectStorageError:
        current_app.logger.exception("Lease document download failed")
        return {"error": "Private file storage is unavailable"}, 503
    response = send_file(
        BytesIO(contents),
        mimetype=document.content_type,
        as_attachment=True,
        download_name=document.filename,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@landlord_tools_bp.route("/reports/portfolio", methods=["GET"])
@jwt_required()
def portfolio_report():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords can view portfolio reports"}, 403
    properties_query = Property.query
    if user.role != "admin":
        properties_query = properties_query.filter_by(owner_id=user.id)
    properties = properties_query.order_by(Property.name, Property.id).all()
    summaries = property_occupancy(properties)
    rows = []
    for property_record in properties:
        income = (
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .join(Lease, Payment.lease_id == Lease.id)
            .join(Unit, Lease.unit_id == Unit.id)
            .filter(
                Unit.property_id == property_record.id,
                Payment.status == "Completed",
                Payment.payment_type == "rent",
            )
            .scalar()
        )
        arrears = (
            db.session.query(
                func.coalesce(func.sum(RentInvoice.amount - RentInvoice.amount_paid), 0)
            )
            .join(Lease, RentInvoice.lease_id == Lease.id)
            .join(Unit, Lease.unit_id == Unit.id)
            .filter(
                Unit.property_id == property_record.id,
                RentInvoice.status.in_(("open", "partial", "overdue")),
                RentInvoice.due_date <= date.today(),
            )
            .scalar()
        )
        summary = summaries[property_record.id]
        rows.append({
            "property_id": property_record.id,
            "property_name": property_record.name,
            "city": property_record.city,
            "currency": property_record.currency,
            "rent_income": float(income or 0),
            "rent_arrears": float(arrears or 0),
            **summary,
        })
    return {
        "generated_at": date.today().isoformat(),
        "properties": rows,
    }, 200
