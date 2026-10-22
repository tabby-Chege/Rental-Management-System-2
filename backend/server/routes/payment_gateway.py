from datetime import datetime, timezone
from decimal import Decimal
from secrets import token_urlsafe

from flask import Blueprint, current_app, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Payment, Property, User
from server.models_application import Application
from server.models_payment import (
    DepositLedgerEntry,
    PaymentAttempt,
    RentInvoice,
    RentSchedule,
)
from server.models_tenant import Tenant, TenantProfile
from server.models_unit_lease import Lease, Unit
from server.money import parse_money
from server.pagination import get_pagination, pagination_metadata
from server.payment_providers import (
    PROVIDER_LABELS,
    PROVIDERS,
    PaymentProviderError,
    configured_providers,
    provider_is_configured,
)
from server.payment_service import (
    add_lease_financial_records,
    finalize_payment_attempt,
    prepare_rent_invoices,
    process_payment_attempt,
    process_rent_schedules,
)
from server.reservations import as_utc, process_reservations


payment_gateway_bp = Blueprint("payment_gateway", __name__, url_prefix="/api/payments")
MANAGER_ROLES = {"landlord", "admin"}
PAYMENT_TYPES = {"reservation", "rent", "deposit"}


def current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def _attempt_visible_to(user, attempt):
    if user.role == "admin":
        return True
    if user.role == "tenant":
        return attempt.user_id == user.id
    if user.role not in MANAGER_ROLES:
        return False
    if attempt.lease_id:
        lease = db.session.get(Lease, attempt.lease_id)
        unit = db.session.get(Unit, lease.unit_id) if lease else None
        prop = db.session.get(Property, unit.property_id) if unit else None
        return bool(prop and prop.owner_id == user.id)
    application = db.session.get(Application, attempt.application_id)
    unit = db.session.get(Unit, application.unit_id) if application else None
    prop = db.session.get(Property, unit.property_id) if unit else None
    return bool(prop and prop.owner_id == user.id)


@payment_gateway_bp.route("/providers", methods=["GET"])
@jwt_required()
def list_payment_providers():
    if not current_user():
        return {"error": "User not found"}, 404
    return {
        "providers": configured_providers(),
        "environment": current_app.config.get("PAYMENT_ENVIRONMENT", "sandbox"),
    }, 200


def _resolve_checkout_target(user, data):
    lease_id = data.get("lease_id")
    application_id = data.get("application_id")
    if (lease_id is None) == (application_id is None):
        return None, None, None, "Provide exactly one of lease_id or application_id"
    if application_id is not None:
        if (
            isinstance(application_id, bool)
            or not isinstance(application_id, int)
            or application_id < 1
        ):
            return None, None, None, "application_id must be a positive integer"
        application = Application.query.filter_by(
            id=application_id, applicant_user_id=user.id
        ).first()
        if not application:
            return None, None, None, "Application not found"
        process_reservations(unit_ids=[application.unit_id], user_id=user.id)
        db.session.refresh(application)
        if application.status not in {"approved", "offered"}:
            return None, None, None, "Application has no active reservation"
        if not application.payment_due_at:
            return None, None, None, "Reservation has no payment deadline"
        if as_utc(application.payment_due_at) <= datetime.now(timezone.utc):
            return None, None, None, "Reservation payment deadline has passed"
        if not application.lease_end_date:
            return None, None, None, "The landlord must set lease terms before checkout"
        unit = db.session.get(Unit, application.unit_id)
        return application, None, unit, None

    if (
        isinstance(lease_id, bool)
        or not isinstance(lease_id, int)
        or lease_id < 1
    ):
        return None, None, None, "lease_id must be a positive integer"
    tenant = Tenant.query.filter_by(user_id=user.id).first()
    lease = (
        Lease.query.filter_by(id=lease_id, tenant_id=tenant.id).first()
        if tenant
        else None
    )
    if not lease:
        return None, None, None, "Lease not found"
    if lease.status != "active":
        return None, None, None, "Payments are only available for active leases"
    unit = db.session.get(Unit, lease.unit_id)
    return None, lease, unit, None


def _expire_attempt_reservation(attempt):
    if attempt.application_id is None:
        return
    application = db.session.get(Application, attempt.application_id)
    if application:
        process_reservations(unit_ids=[application.unit_id])
        db.session.refresh(attempt)


@payment_gateway_bp.route("/checkout", methods=["POST"])
@jwt_required()
def create_checkout():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role != "tenant":
        return {"error": "Only tenants can start online payments"}, 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    allowed = {
        "provider",
        "lease_id",
        "application_id",
        "amount",
        "payment_type",
        "phone_number",
    }
    if set(data) - allowed:
        return {"error": "Unsupported checkout fields"}, 400
    provider = data.get("provider")
    if provider not in {*PROVIDERS, "bank_transfer"}:
        return {"error": "Unsupported payment provider"}, 400
    if provider != "bank_transfer" and not provider_is_configured(provider):
        return {"error": "Payment provider is not configured"}, 503

    application, lease, unit, error = _resolve_checkout_target(user, data)
    if error:
        return {"error": error}, 404 if error in {"Application not found", "Lease not found"} else 409
    if not unit or not unit.property:
        return {"error": "Payment target has no valid property"}, 409

    payment_type = data.get(
        "payment_type", "reservation" if application else "rent"
    )
    if payment_type not in PAYMENT_TYPES:
        return {"error": "payment_type must be reservation, rent, or deposit"}, 400
    if application and payment_type != "reservation":
        return {"error": "Application checkout must use the reservation payment type"}, 400
    if lease and payment_type == "reservation":
        return {"error": "Reservation payment type requires an approved application"}, 400

    amount, amount_error = parse_money(data.get("amount"), unit.property.currency)
    if amount_error:
        return {"error": amount_error}, 400
    if provider == "mpesa" and unit.property.currency != "KES":
        return {"error": "M-Pesa checkout is available only for KES properties"}, 400
    phone_number = data.get("phone_number")
    if phone_number is not None and (
        not isinstance(phone_number, str) or len(phone_number) > 20
    ):
        return {"error": "phone_number must be text of at most 20 characters"}, 400
    if provider == "mpesa" and not phone_number:
        profile = TenantProfile.query.filter_by(user_id=user.id).first()
        phone_number = profile.phone if profile else None
    if provider == "mpesa" and not phone_number:
        return {"error": "A verified tenant phone number is required for M-Pesa"}, 400

    if payment_type == "deposit" and lease:
        add_lease_financial_records(lease)
        charged = (
            db.session.query(func.coalesce(func.sum(DepositLedgerEntry.amount), 0))
            .filter(
                DepositLedgerEntry.lease_id == lease.id,
                DepositLedgerEntry.entry_type == "charge",
            )
            .scalar()
        )
        paid = (
            db.session.query(func.coalesce(func.sum(DepositLedgerEntry.amount), 0))
            .filter(
                DepositLedgerEntry.lease_id == lease.id,
                DepositLedgerEntry.entry_type == "payment",
            )
            .scalar()
        )
        deposit_balance = Decimal(charged or 0) - Decimal(paid or 0)
        if deposit_balance <= 0:
            return {"error": "There is no outstanding deposit balance"}, 409
        if amount > deposit_balance:
            return {"error": "Payment exceeds the outstanding deposit balance"}, 400
    if lease and payment_type == "rent":
        try:
            prepare_rent_invoices(lease, amount)
        except ValueError as validation_error:
            db.session.rollback()
            return {"error": str(validation_error)}, 400

    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key:
        idempotency_key = token_urlsafe(24)
    if len(idempotency_key) > 80:
        return {"error": "Idempotency-Key must be 80 characters or fewer"}, 400
    existing = PaymentAttempt.query.filter_by(
        idempotency_key=idempotency_key
    ).first()
    if existing:
        if (
            existing.user_id != user.id
            or existing.provider != provider
            or existing.lease_id != (lease.id if lease else None)
            or existing.application_id != (application.id if application else None)
            or Decimal(existing.amount) != amount
            or existing.payment_type != payment_type
            or existing.currency != unit.property.currency
        ):
            return {"error": "Idempotency-Key was already used for another payment"}, 409
        return {"attempt": existing.to_dict()}, 200

    attempt = PaymentAttempt(
        user_id=user.id,
        lease_id=lease.id if lease else None,
        application_id=application.id if application else None,
        idempotency_key=idempotency_key,
        provider=provider,
        amount=amount,
        currency=unit.property.currency,
        payment_type=payment_type,
        customer_email=user.email,
        phone_number=phone_number,
        lease_end_date=application.lease_end_date if application else None,
    )
    db.session.add(attempt)
    db.session.commit()

    if provider == "bank_transfer":
        attempt.provider_data = {
            "instructions": current_app.config.get(
                "BANK_TRANSFER_INSTRUCTIONS", ""
            )
        }
        db.session.commit()
        return {"attempt": attempt.to_dict()}, 201

    try:
        checkout = PROVIDERS[provider].create_checkout(attempt)
    except PaymentProviderError as provider_error:
        attempt.status = "failed"
        db.session.commit()
        return {
            "error": str(provider_error),
            "attempt": attempt.to_dict(),
        }, 502

    attempt.provider_reference = checkout["provider_reference"]
    attempt.checkout_url = checkout["checkout_url"]
    attempt.provider_data = checkout["provider_data"]
    db.session.commit()
    return {"attempt": attempt.to_dict()}, 201


@payment_gateway_bp.route("/attempts/<int:attempt_id>", methods=["GET"])
@jwt_required()
def get_payment_attempt(attempt_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    attempt = db.session.get(PaymentAttempt, attempt_id)
    if not attempt or not _attempt_visible_to(user, attempt):
        return {"error": "Payment attempt not found"}, 404
    _expire_attempt_reservation(attempt)
    if attempt.status == "pending" and attempt.provider != "bank_transfer":
        try:
            process_payment_attempt(attempt, PROVIDERS[attempt.provider])
        except PaymentProviderError as provider_error:
            db.session.rollback()
            return {"error": str(provider_error)}, 502
        except ValueError as validation_error:
            db.session.rollback()
            return {"error": str(validation_error)}, 409
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return {"error": "Payment confirmation conflicts with another record"}, 409
    return {"attempt": attempt.to_dict()}, 200


@payment_gateway_bp.route("/attempts", methods=["GET"])
@jwt_required()
def list_payment_attempts():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    query = PaymentAttempt.query
    if user.role == "tenant":
        query = query.filter(PaymentAttempt.user_id == user.id)
    elif user.role in MANAGER_ROLES:
        if user.role != "admin":
            lease_ids = (
                db.session.query(Lease.id)
                .join(Unit, Lease.unit_id == Unit.id)
                .join(Property, Unit.property_id == Property.id)
                .filter(Property.owner_id == user.id)
            )
            application_ids = (
                db.session.query(Application.id)
                .join(Unit, Application.unit_id == Unit.id)
                .join(Property, Unit.property_id == Property.id)
                .filter(Property.owner_id == user.id)
            )
            query = query.filter(
                or_(
                    PaymentAttempt.lease_id.in_(lease_ids),
                    PaymentAttempt.application_id.in_(application_ids),
                )
            )
    else:
        return {"error": "You do not have permission to view payment attempts"}, 403
    status = request.args.get("status")
    if status:
        if status not in {"pending", "completed", "failed", "refund_required"}:
            return {
                "error": "status must be pending, completed, failed, or refund_required"
            }, 400
        query = query.filter(PaymentAttempt.status == status)
    result = query.order_by(
        PaymentAttempt.created_at.desc(), PaymentAttempt.id.desc()
    ).limit(100).all()
    return {"attempts": [attempt.to_dict() for attempt in result]}, 200


@payment_gateway_bp.route(
    "/attempts/<int:attempt_id>/confirm", methods=["POST"]
)
@jwt_required()
def confirm_bank_transfer(attempt_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can confirm transfers"}, 403
    attempt = db.session.get(PaymentAttempt, attempt_id)
    if (
        not attempt
        or not _attempt_visible_to(user, attempt)
        or attempt.provider != "bank_transfer"
    ):
        return {"error": "Bank transfer attempt not found"}, 404
    _expire_attempt_reservation(attempt)
    if attempt.status == "completed":
        return {"attempt": attempt.to_dict()}, 200
    if attempt.status != "pending":
        return {"error": "Only pending transfers can be confirmed"}, 409
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"provider_reference"}:
        return {"error": "Request body must contain provider_reference"}, 400
    reference = data.get("provider_reference")
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 160:
        return {"error": "provider_reference must be non-empty text of at most 160 characters"}, 400
    try:
        finalize_payment_attempt(
            attempt,
            {
                "status": "completed",
                "provider_reference": reference.strip(),
                "amount": Decimal(attempt.amount),
                "currency": attempt.currency,
            },
        )
        db.session.commit()
    except ValueError as validation_error:
        db.session.rollback()
        return {"error": str(validation_error)}, 409
    except IntegrityError:
        db.session.rollback()
        return {"error": "Transfer reference has already been recorded"}, 409
    return {"attempt": attempt.to_dict()}, 200


def _process_provider_webhook(provider_name, payload):
    provider = PROVIDERS.get(provider_name)
    if not provider:
        return {"error": "Unsupported payment provider"}, 404
    if not provider_is_configured(provider_name):
        return {"error": "Payment provider is not configured"}, 503
    try:
        valid_signature = provider.validate_webhook(request)
    except PaymentProviderError as provider_error:
        return {"error": str(provider_error)}, 502
    if not valid_signature:
        return {"error": "Invalid payment provider signature"}, 401
    reference = provider.webhook_reference(payload)
    if not reference:
        return {"error": "Webhook is missing a payment reference"}, 400
    attempt = PaymentAttempt.query.filter_by(
        provider=provider_name, provider_reference=str(reference)
    ).first()
    if not attempt:
        return {"error": "Payment attempt not found"}, 404
    _expire_attempt_reservation(attempt)
    if attempt.status == "completed":
        return {"received": True, "status": "completed"}, 200
    try:
        result = provider.verify(attempt, payload)
        finalize_payment_attempt(attempt, result)
        db.session.commit()
    except PaymentProviderError as provider_error:
        db.session.rollback()
        return {"error": str(provider_error)}, 502
    except ValueError as validation_error:
        db.session.rollback()
        return {"error": str(validation_error)}, 409
    except IntegrityError:
        db.session.rollback()
        return {"error": "Payment confirmation conflicts with another record"}, 409
    return {"received": True, "status": attempt.status}, 200


@payment_gateway_bp.route(
    "/webhooks/<provider_name>", methods=["GET", "POST"]
)
def payment_webhook(provider_name):
    payload = (
        request.get_json(silent=True)
        if request.method == "POST"
        else request.args.to_dict()
    )
    if not isinstance(payload, dict):
        return {"error": "Webhook body must be a JSON object"}, 400
    if (
        provider_name == "stripe"
        and payload.get("type")
        not in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        }
    ):
        provider = PROVIDERS.get(provider_name)
        if not provider:
            return {"error": "Unsupported payment provider"}, 404
        if not provider_is_configured(provider_name):
            return {"error": "Payment provider is not configured"}, 503
        try:
            valid_signature = provider.validate_webhook(request)
        except PaymentProviderError as provider_error:
            return {"error": str(provider_error)}, 502
        if not valid_signature:
            return {"error": "Invalid payment provider signature"}, 401
        return {"received": True, "ignored": True}, 200
    response, status = _process_provider_webhook(provider_name, payload)
    if provider_name == "pesapal" and status in {200, 202}:
        return {
            "orderNotificationType": request.args.get("OrderNotificationType", ""),
            "orderTrackingId": request.args.get("OrderTrackingId", ""),
            "orderMerchantReference": request.args.get("OrderMerchantReference", ""),
            "status": 200,
        }, 200
    return response, status


@payment_gateway_bp.route("/invoices", methods=["GET"])
@jwt_required()
def list_rent_invoices():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES and user.role != "tenant":
        return {"error": "You do not have permission to view rent invoices"}, 403
    leases_query = Lease.query.join(Unit).join(Property)
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        leases_query = leases_query.filter(
            Lease.tenant_id == tenant.id if tenant else Lease.id == -1
        )
    elif user.role != "admin":
        leases_query = leases_query.filter(Property.owner_id == user.id)
    for lease in leases_query.all():
        add_lease_financial_records(lease)
    db.session.commit()
    process_rent_schedules()
    query = RentInvoice.query.join(Lease, RentInvoice.lease_id == Lease.id).join(
        Unit, Lease.unit_id == Unit.id
    ).join(Property, Unit.property_id == Property.id)
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        query = query.filter(
            Lease.tenant_id == tenant.id if tenant else Lease.id == -1
        )
    elif user.role != "admin":
        query = query.filter(Property.owner_id == user.id)

    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    result = query.order_by(
        RentInvoice.due_date.desc(), RentInvoice.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return {
        "invoices": [invoice.to_dict() for invoice in result.items],
        "pagination": pagination_metadata(result),
    }, 200


@payment_gateway_bp.route("/deposits", methods=["GET", "POST"])
@jwt_required()
def deposit_ledger():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES and user.role != "tenant":
        return {"error": "You do not have permission to view deposit records"}, 403
    if request.method == "POST":
        if user.role not in MANAGER_ROLES:
            return {"error": "Only landlords and admins can record deposit adjustments"}, 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) - {
            "lease_id",
            "entry_type",
            "amount",
            "note",
        }:
            return {"error": "Invalid deposit ledger request"}, 400
        lease_id = data.get("lease_id")
        if isinstance(lease_id, bool) or not isinstance(lease_id, int) or lease_id < 1:
            return {"error": "lease_id must be a positive integer"}, 400
        lease = Lease.query.join(Unit).join(Property).filter(Lease.id == lease_id)
        if user.role != "admin":
            lease = lease.filter(Property.owner_id == user.id)
        lease = lease.first()
        if not lease:
            return {"error": "Lease not found"}, 404
        entry_type = data.get("entry_type")
        if entry_type not in {"charge", "refund"}:
            return {"error": "entry_type must be charge or refund"}, 400
        currency = lease.unit.property.currency
        amount, amount_error = parse_money(data.get("amount"), currency)
        if amount_error:
            return {"error": amount_error}, 400
        note = data.get("note")
        if note is not None and (
            not isinstance(note, str) or len(note.strip()) > 500
        ):
            return {"error": "note must be text of at most 500 characters"}, 400
        if entry_type == "refund":
            paid = (
                db.session.query(func.coalesce(func.sum(DepositLedgerEntry.amount), 0))
                .filter(
                    DepositLedgerEntry.lease_id == lease.id,
                    DepositLedgerEntry.entry_type == "payment",
                )
                .scalar()
            )
            refunded = (
                db.session.query(func.coalesce(func.sum(DepositLedgerEntry.amount), 0))
                .filter(
                    DepositLedgerEntry.lease_id == lease.id,
                    DepositLedgerEntry.entry_type == "refund",
                )
                .scalar()
            )
            if amount > Decimal(paid or 0) - Decimal(refunded or 0):
                return {"error": "Refund exceeds the held deposit balance"}, 409
        entry = DepositLedgerEntry(
            lease_id=lease.id,
            entry_type=entry_type,
            amount=amount,
            currency=currency,
            note=note.strip() if isinstance(note, str) else None,
        )
        db.session.add(entry)
        db.session.commit()
        return {"entry": entry.to_dict()}, 201

    raw_lease_id = request.args.get("lease_id")
    leases_query = Lease.query.join(Unit).join(Property)
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        leases_query = leases_query.filter(
            Lease.tenant_id == tenant.id if tenant else Lease.id == -1
        )
    elif user.role != "admin":
        leases_query = leases_query.filter(Property.owner_id == user.id)
    if raw_lease_id:
        if not raw_lease_id.isdecimal() or int(raw_lease_id) < 1:
            return {"error": "lease_id must be a positive integer"}, 400
        leases_query = leases_query.filter(Lease.id == int(raw_lease_id))
    for lease in leases_query.all():
        add_lease_financial_records(lease)
    db.session.commit()

    query = DepositLedgerEntry.query.join(Lease).join(Unit).join(Property)
    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        query = query.filter(
            Lease.tenant_id == tenant.id if tenant else Lease.id == -1
        )
    elif user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    if raw_lease_id:
        query = query.filter(Lease.id == int(raw_lease_id))
    entries = query.order_by(
        DepositLedgerEntry.created_at.desc(), DepositLedgerEntry.id.desc()
    ).all()
    balances = {}
    for entry in entries:
        balance = balances.setdefault(
            entry.lease_id,
            {
                "lease_id": entry.lease_id,
                "currency": entry.currency,
                "charged": Decimal("0"),
                "paid": Decimal("0"),
                "refunded": Decimal("0"),
            },
        )
        if entry.entry_type == "charge":
            balance["charged"] += Decimal(entry.amount)
        elif entry.entry_type == "payment":
            balance["paid"] += Decimal(entry.amount)
        elif entry.entry_type == "refund":
            balance["refunded"] += Decimal(entry.amount)
    for balance in balances.values():
        balance["outstanding"] = balance["charged"] - balance["paid"]
        balance["held"] = balance["paid"] - balance["refunded"]
        for key in ("charged", "paid", "refunded", "outstanding", "held"):
            balance[key] = float(balance[key])
    return {
        "entries": [entry.to_dict() for entry in entries],
        "balances": list(balances.values()),
    }, 200
