from datetime import date, timedelta

from flask import Blueprint, current_app, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Payment, Property, User
from server.models_application import (
    APPLICATION_STATUSES,
    RESERVED_APPLICATION_STATUSES,
    Application,
)
from server.models_tenant import Tenant, TenantDocument, TenantProfile
from server.models_unit_lease import Lease, Unit
from server.money import parse_money
from server.occupancy import property_json, property_occupancy, unit_occupancy
from server.pagination import get_pagination, pagination_metadata
from server.payment_service import add_lease_financial_records, queue_email
from server.reservations import (
    add_reservation_notification,
    as_utc,
    process_reservations,
    reservation_deadline,
    utc_now,
)
from server.routes.payment import PAYMENT_METHODS
from server.tenant_security import TenantDataProtectionError, decrypt_id_number

applications_bp = Blueprint(
    "applications", __name__, url_prefix="/api/applications"
)
MANAGER_ROLES = {"landlord", "admin"}
MAX_MESSAGE_LENGTH = 5000


def current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def owned_application_query(user):
    query = Application.query.join(Unit).join(Property)
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query


def parse_application_data(data):
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object"
    unknown = set(data) - {"unit_id", "message", "move_in_date"}
    if unknown:
        return None, "Unsupported fields: " + ", ".join(sorted(unknown))

    unit_id = data.get("unit_id")
    if isinstance(unit_id, bool) or not isinstance(unit_id, int) or unit_id < 1:
        return None, "unit_id must be a positive integer"

    message = data.get("message", "")
    if message is not None and not isinstance(message, str):
        return None, "message must be text"
    message = (message or "").strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return None, f"message must be {MAX_MESSAGE_LENGTH} characters or fewer"

    try:
        move_in_date = date.fromisoformat(data.get("move_in_date"))
    except (TypeError, ValueError):
        return None, "move_in_date must be a date in YYYY-MM-DD format"

    return {
        "unit_id": unit_id,
        "message": message or None,
        "move_in_date": move_in_date,
    }, None


def visible_application(user, application_id):
    if user.role == "tenant":
        return Application.query.filter_by(
            id=application_id, applicant_user_id=user.id
        ).first()
    if user.role in MANAGER_ROLES:
        return owned_application_query(user).filter(
            Application.id == application_id
        ).first()
    return None


def application_payload(application):
    payload = application.to_dict()
    snapshot = dict(application.profile_snapshot or {})
    encrypted_id_number = snapshot.pop("encrypted_id_number", None)
    try:
        snapshot["id_number"] = decrypt_id_number(encrypted_id_number)
    except TenantDataProtectionError:
        current_app.logger.exception(
            "Unable to decrypt applicant ID details for application %s",
            application.id,
        )
        raise
    payload["applicant_profile"] = snapshot
    unit = db.session.get(Unit, application.unit_id)
    prop = db.session.get(Property, unit.property_id) if unit else None
    applicant = db.session.get(User, application.applicant_user_id)
    if unit:
        occupancy = unit_occupancy([unit.id])[unit.id]
        payload["unit"] = unit.to_dict(
            occupancy["lease"],
            occupancy["is_reserved"],
        )
    else:
        payload["unit"] = None
    payload["property"] = (
        property_json(prop, property_occupancy([prop])[prop.id]) if prop else None
    )
    payload["applicant"] = {
        "id": applicant.id if applicant else application.applicant_user_id,
        "name": snapshot.get("full_name") or (applicant.name if applicant else None),
        "email": snapshot.get("email") or (applicant.email if applicant else None),
    }
    return payload


@applications_bp.route("", methods=["GET"])
@jwt_required()
def list_applications():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role == "tenant":
        unit_ids = db.session.query(Application.unit_id).filter_by(
            applicant_user_id=user.id
        ).distinct()
        process_reservations(
            unit_ids=(unit_id for (unit_id,) in unit_ids)
        )
    else:
        process_reservations()

    if user.role == "tenant":
        query = Application.query.filter_by(applicant_user_id=user.id)
    elif user.role in MANAGER_ROLES:
        query = owned_application_query(user)
    else:
        return {"error": "You do not have permission to view applications"}, 403

    status = request.args.get("status")
    if status:
        if status not in APPLICATION_STATUSES:
            return {"error": "Invalid application status"}, 400
        query = query.filter(Application.status == status)

    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    result = query.order_by(
        Application.created_at.desc(), Application.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    try:
        items = [application_payload(application) for application in result.items]
    except TenantDataProtectionError:
        return {"error": "Applicant ID details are unavailable"}, 503
    return {
        "applications": items,
        "pagination": pagination_metadata(result),
    }, 200


@applications_bp.route("", methods=["POST"])
@jwt_required()
def create_application():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role != "tenant":
        return {"error": "Only tenants can apply for units"}, 403
    profile = TenantProfile.query.filter_by(user_id=user.id).first()
    if not profile:
        return {"error": "Complete your tenant profile before applying"}, 409

    values, error = parse_application_data(request.get_json(silent=True))
    if error:
        return {"error": error}, 400
    unit = Unit.query.filter_by(id=values["unit_id"]).first()
    if not unit:
        return {"error": "Unit not found"}, 404
    status = unit_occupancy([unit.id])[unit.id]
    if status["lease"]:
        return {"error": "This unit is not available for applications"}, 409

    pending = Application.query.filter(
        Application.unit_id == unit.id,
        Application.applicant_user_id == user.id,
        Application.status.in_(
            ("pending", "waitlisted", "approved", "offered", "paid")
        ),
    ).first()
    if pending:
        return {"error": "You already have a pending application for this unit"}, 409

    documents = TenantDocument.query.filter_by(user_id=user.id).all()
    profile_snapshot = {
        "full_name": profile.full_name,
        "email": user.email,
        "phone": profile.phone,
        "employment_status": profile.employment_status,
        "employer": profile.employer,
        "job_title": profile.job_title,
        "emergency_contact_name": profile.emergency_contact_name,
        "emergency_contact_phone": profile.emergency_contact_phone,
        "emergency_contact_relationship": profile.emergency_contact_relationship,
        "id_type": profile.id_type,
        "encrypted_id_number": profile.encrypted_id_number,
        "previous_landlord_name": profile.previous_landlord_name,
        "previous_landlord_contact": profile.previous_landlord_contact,
        "document_ids": [document.id for document in documents],
        "documents": [document.to_dict() for document in documents],
    }
    application = Application(
        unit_id=unit.id,
        applicant_user_id=user.id,
        message=values["message"],
        move_in_date=values["move_in_date"],
        profile_snapshot=profile_snapshot,
        status="waitlisted" if status["is_reserved"] else "pending",
    )
    db.session.add(application)
    db.session.commit()
    try:
        payload = application_payload(application)
    except TenantDataProtectionError:
        return {"error": "Applicant ID details are unavailable"}, 503
    return {
        "message": (
            "Added to the waitlist"
            if application.status == "waitlisted"
            else "Application submitted"
        ),
        "application": payload,
    }, 201


@applications_bp.route("/<int:application_id>", methods=["GET"])
@jwt_required()
def get_application(application_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    application = visible_application(user, application_id)
    if not application:
        return {"error": "Application not found"}, 404
    process_reservations(unit_ids=[application.unit_id])
    db.session.refresh(application)
    try:
        payload = application_payload(application)
    except TenantDataProtectionError:
        return {"error": "Applicant ID details are unavailable"}, 503
    return {"application": payload}, 200


@applications_bp.route("/<int:application_id>", methods=["PATCH"])
@jwt_required()
def decide_application(application_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can decide applications"}, 403

    visible = visible_application(user, application_id)
    if not visible:
        return {"error": "Application not found"}, 404
    process_reservations(unit_ids=[visible.unit_id])
    unit = (
        Unit.query.filter_by(id=visible.unit_id)
        .with_for_update()
        .first()
    )
    application = visible_application(user, application_id)
    if not application or not unit:
        return {"error": "Application not found"}, 404

    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or not {"status"} <= set(data)
        or set(data) - {"status", "reason"}
    ):
        return {"error": "Request body must contain status and optional reason"}, 400
    decision = data["status"]
    if decision not in ("approved", "declined"):
        return {"error": "status must be approved or declined"}, 400
    reason = data.get("reason")
    if reason is not None and not isinstance(reason, str):
        return {"error": "reason must be text"}, 400
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) > 1000:
        return {"error": "reason must be 1000 characters or fewer"}, 400
    if not reason:
        return {"error": "A reason is required for every application decision"}, 400
    if decision == "approved" and application.status != "pending":
        return {"error": "Only pending applications can be approved"}, 409
    if decision == "declined" and application.status not in {
        "pending",
        "waitlisted",
    }:
        return {"error": "Only pending or waitlisted applications can be declined"}, 409

    property_record = db.session.get(Property, unit.property_id)
    owner_id = property_record.owner_id
    tenant = None
    if decision == "approved":
        local_today = date.today()
        active_lease = Lease.query.filter(
            Lease.unit_id == unit.id,
            Lease.status == "active",
            Lease.start_date <= local_today,
            Lease.end_date >= local_today,
        ).first()
        if active_lease:
            return {"error": "This unit already has an active lease"}, 409
        active_reservation = Application.query.filter(
            Application.unit_id == unit.id,
            Application.id != application.id,
            Application.status.in_(RESERVED_APPLICATION_STATUSES),
        ).first()
        if active_reservation:
            return {"error": "This unit already has an approved application"}, 409
        waiting_before = Application.query.filter(
            Application.unit_id == unit.id,
            Application.id != application.id,
            Application.status == "waitlisted",
        ).first()
        if waiting_before:
            return {"error": "The next waitlisted applicant must be offered the unit"}, 409
        tenant = Tenant.query.filter_by(
            user_id=application.applicant_user_id
        ).first()
        if tenant and tenant.landlord_id != owner_id:
            return {
                "error": "Applicant account is already linked to another landlord"
            }, 409
        if not tenant:
            applicant = db.session.get(User, application.applicant_user_id)
            duplicate_email = Tenant.query.filter_by(
                landlord_id=owner_id, email=applicant.email
            ).first()
            if duplicate_email:
                return {
                    "error": "A tenant with the applicant's email already exists"
                }, 409
            tenant = Tenant(
                landlord_id=owner_id,
                user_id=applicant.id,
                name=applicant.name,
                email=applicant.email,
            )
            db.session.add(tenant)
            db.session.flush()
        application.tenant_id = tenant.id

    application.status = decision
    application.decision_reason = reason or None
    if decision == "approved":
        application.payment_due_at = reservation_deadline(utc_now())
        waitlisted = Application.query.filter(
            Application.unit_id == unit.id,
            Application.id != application.id,
            Application.status == "pending",
        ).with_for_update().all()
        for queued in waitlisted:
            queued.status = "waitlisted"
        add_reservation_notification(
            application,
            "reservation_approved",
            "Your application was approved. Confirm payment before the reservation deadline.",
            application.payment_due_at,
        )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "The unit was reserved by another application"}, 409

    try:
        payload = application_payload(application)
    except TenantDataProtectionError:
        return {"error": "Applicant ID details are unavailable"}, 503
    response = {
        "message": f"Application {decision}",
        "application": payload,
    }
    if decision == "approved":
        response["tenant"] = tenant.to_dict()
    return response, 200


@applications_bp.route("/<int:application_id>/lease-terms", methods=["PATCH"])
@jwt_required()
def set_reservation_lease_terms(application_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can set lease terms"}, 403
    application = visible_application(user, application_id)
    if not application:
        return {"error": "Application not found"}, 404
    process_reservations(unit_ids=[application.unit_id])
    application = visible_application(user, application_id)
    if not application or application.status not in {"approved", "offered"}:
        return {"error": "Lease terms can only be set for an active reservation"}, 409
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"lease_end_date"}:
        return {"error": "Request body must contain lease_end_date"}, 400
    try:
        end_date = date.fromisoformat(data["lease_end_date"])
    except (TypeError, ValueError):
        return {"error": "lease_end_date must use YYYY-MM-DD format"}, 400
    if end_date <= application.move_in_date:
        return {"error": "lease_end_date must be after the requested move-in date"}, 400
    application.lease_end_date = end_date
    db.session.commit()
    return {"application": application_payload(application)}, 200


@applications_bp.route(
    "/<int:application_id>/confirm-payment", methods=["POST"]
)
@jwt_required()
def confirm_reservation_payment(application_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can confirm reservation payments"}, 403

    visible = visible_application(user, application_id)
    if not visible:
        return {"error": "Application not found"}, 404
    process_reservations(unit_ids=[visible.unit_id])
    unit = Unit.query.filter_by(id=visible.unit_id).with_for_update().first()
    application = (
        owned_application_query(user)
        .filter(Application.id == application_id)
        .with_for_update()
        .first()
    )
    if not application or not unit:
        return {"error": "Application not found"}, 404

    if application.status in {"paid", "leased"} and application.lease_id:
        lease = db.session.get(Lease, application.lease_id)
        payment = (
            Payment.query.filter_by(lease_id=lease.id)
            .order_by(Payment.id.desc())
            .first()
            if lease
            else None
        )
        if lease and payment:
            return {
                "message": "Reservation payment was already confirmed",
                "application": application_payload(application),
                "lease": lease.to_dict(),
                "payment": payment.to_dict(),
            }, 200
        return {"error": "The confirmed reservation is missing its lease or payment"}, 409

    if application.status not in {"approved", "offered"}:
        return {"error": "This application has no active reservation"}, 409
    now = utc_now()
    due_at = as_utc(application.payment_due_at) if application.payment_due_at else None
    if not due_at or due_at <= now:
        process_reservations(unit_ids=[unit.id])
        return {"error": "The reservation payment deadline has passed"}, 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    allowed_fields = {"amount", "payment_method", "reference_code", "lease_end_date"}
    if set(data) - allowed_fields:
        return {"error": "Unsupported reservation payment fields"}, 400
    payment_method = data.get("payment_method")
    if payment_method not in PAYMENT_METHODS:
        return {"error": "payment_method must be M-Pesa, Bank Transfer, or Cash"}, 400
    raw_end_date = data.get("lease_end_date")
    if raw_end_date is None:
        lease_end_date = application.lease_end_date
    else:
        try:
            lease_end_date = date.fromisoformat(raw_end_date)
        except (TypeError, ValueError):
            return {"error": "lease_end_date must use YYYY-MM-DD format"}, 400
    if not lease_end_date:
        return {"error": "Set lease terms before confirming payment"}, 400
    if lease_end_date <= application.move_in_date:
        return {"error": "lease_end_date must be after the requested move-in date"}, 400
    amount, amount_error = parse_money(data.get("amount"), unit.property.currency)
    if amount_error:
        return {"error": amount_error}, 400
    reference_code = data.get("reference_code")
    if reference_code is not None:
        if not isinstance(reference_code, str):
            return {"error": "reference_code must be text"}, 400
        reference_code = reference_code.strip() or None
        if reference_code and len(reference_code) > 100:
            return {"error": "reference_code is too long"}, 400
    if not application.tenant_id or unit.rent_amount is None:
        return {"error": "The approved application is missing lease details"}, 409

    conflicting_lease = Lease.query.filter(
        Lease.unit_id == unit.id,
        Lease.status == "active",
        Lease.start_date <= lease_end_date,
        Lease.end_date >= application.move_in_date,
    ).first()
    if conflicting_lease:
        return {"error": "The unit already has a lease for those dates"}, 409

    lease = Lease(
        unit_id=unit.id,
        tenant_id=application.tenant_id,
        start_date=application.move_in_date,
        end_date=lease_end_date,
        monthly_rent=unit.rent_amount,
        deposit=0,
        status="active",
    )
    db.session.add(lease)
    db.session.flush()
    add_lease_financial_records(lease)
    payment = Payment(
        lease_id=lease.id,
        amount=amount,
        currency=unit.property.currency,
        payment_method=payment_method,
        status="Completed",
        reference_code=reference_code,
        provider="manual",
        provider_reference=reference_code,
        payment_type="reservation",
    )
    db.session.add(payment)
    application.lease_id = lease.id
    application.lease_end_date = lease_end_date
    application.status = "paid"
    add_reservation_notification(
        application,
        "payment_confirmed",
        "Your reservation payment was confirmed and your lease has been created.",
        now,
    )
    applicant = db.session.get(User, application.applicant_user_id)
    queue_email(
        f"payment:{application.id}:manual-reservation-receipt",
        applicant.email if applicant else None,
        f"Reservation payment receipt for lease {lease.id}",
        (
            f"Payment received: {unit.property.currency} {amount}. "
            f"Provider: manual ({payment_method}). "
            f"Reference: {reference_code or 'not provided'}."
        ),
    )
    waitlisted = Application.query.filter(
        Application.unit_id == unit.id,
        Application.status == "waitlisted",
    ).with_for_update().all()
    for queued in waitlisted:
        queued.status = "declined"
        queued.decision_reason = "The unit was leased to another applicant."
        add_reservation_notification(
            queued,
            "waitlist_closed",
            "The unit was leased to another applicant.",
            now,
        )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "The payment reference or lease conflicts with another record"}, 409

    return {
        "message": "Reservation payment confirmed",
        "application": application_payload(application),
        "lease": lease.to_dict(),
        "payment": payment.to_dict(),
    }, 201
