from sqlalchemy import false
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Payment, Property, User
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit
from server.money import parse_money
from server.models_payment import DepositLedgerEntry
from server.pagination import get_pagination, pagination_metadata
from server.payment_service import (
    add_lease_financial_records,
    apply_payment_effects,
    prepare_rent_invoices,
)

payments_bp = Blueprint("payments_bp", __name__)

MANAGER_ROLES = {"landlord", "admin"}
PAYMENT_METHODS = {"M-Pesa", "Bank Transfer", "Cash"}
PAYMENT_STATUSES = {"Pending", "Completed", "Failed"}


def current_user():
    """Return the authenticated user, or None if the account no longer exists."""
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None

    return db.session.get(User, user_id)


def payment_query_for_user(user):
    """Return only payments the authenticated user is allowed to view."""
    query = (
        Payment.query
        .join(Lease, Payment.lease_id == Lease.id)
        .join(Unit, Lease.unit_id == Unit.id)
        .join(Property, Unit.property_id == Property.id)
    )

    if user.role == "admin":
        return query

    if user.role == "landlord":
        return query.filter(Property.owner_id == user.id)

    if user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()

        if not tenant:
            return query.filter(false())

        return query.filter(Lease.tenant_id == tenant.id)

    return query.filter(false())


@payments_bp.route("/payments", methods=["GET"])
@payments_bp.route("/api/payments", methods=["GET"])
@jwt_required()
def get_payments():
    user = current_user()

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.role not in MANAGER_ROLES and user.role != "tenant":
        return jsonify({"error": "You do not have permission to view payments"}), 403

    pagination, error = get_pagination()
    if error:
        return jsonify({"error": error}), 400
    page, per_page = pagination
    result = (
        payment_query_for_user(user)
        .join(Tenant, Lease.tenant_id == Tenant.id)
        .add_columns(
            Tenant.name,
            Property.name,
            Unit.unit_number,
            Lease.tenant_id,
            Lease.unit_id,
            Property.id,
        )
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        "payments": [
            {
                **payment.to_dict(),
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
                "property_id": property_id,
                "property_name": property_name,
                "unit_id": unit_id,
                "unit_number": unit_number,
            }
            for (
                payment,
                tenant_name,
                property_name,
                unit_number,
                tenant_id,
                unit_id,
                property_id,
            ) in result.items
        ],
        "pagination": pagination_metadata(result),
    }), 200


@payments_bp.route("/api/payments", methods=["POST"])
@payments_bp.route("/payments", methods=["POST"])
@jwt_required()
def create_payment():
    user = current_user()

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Tenants may view their own payments, but cannot create payment records.
    if user.role not in MANAGER_ROLES:
        return jsonify({"error": "Only landlords and admins can record payments"}), 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON"}), 400

    lease_id = data.get("lease_id")
    raw_amount = data.get("amount")
    payment_method = data.get("payment_method")
    status = data.get("status", "Pending")
    reference_code = data.get("reference_code")
    payment_type = data.get("payment_type", "rent")
    if set(data) - {
        "lease_id",
        "amount",
        "payment_method",
        "status",
        "reference_code",
        "payment_type",
    }:
        return jsonify({"error": "Unsupported payment fields"}), 400

    if isinstance(lease_id, bool) or not isinstance(lease_id, int) or lease_id <= 0:
        return jsonify({"error": "lease_id must be a positive integer"}), 400

    if payment_method not in PAYMENT_METHODS:
        return jsonify({
            "error": "payment_method must be M-Pesa, Bank Transfer, or Cash"
        }), 400

    if status not in PAYMENT_STATUSES:
        return jsonify({
            "error": "status must be Pending, Completed, or Failed"
        }), 400
    if payment_type not in {"reservation", "rent", "deposit", "other"}:
        return jsonify({
            "error": "payment_type must be reservation, rent, deposit, or other"
        }), 400

    if reference_code is not None:
        if not isinstance(reference_code, str):
            return jsonify({"error": "reference_code must be text"}), 400

        reference_code = reference_code.strip() or None

        if reference_code and len(reference_code) > 100:
            return jsonify({"error": "reference_code is too long"}), 400

    lease = db.session.get(Lease, lease_id)

    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    unit = db.session.get(Unit, lease.unit_id)
    prop = db.session.get(Property, unit.property_id) if unit else None
    if not prop:
        return jsonify({"error": "The lease has no valid property"}), 409
    amount, amount_error = parse_money(raw_amount, prop.currency)
    if amount_error:
        return jsonify({"error": amount_error}), 400

    # Admins can manage payments system-wide.
    # Landlords can only record payments for leases on their own properties.
    if user.role != "admin" and prop.owner_id != user.id:
        return jsonify({
            "error": "You do not have permission to record payment for this lease"
        }), 403

    if payment_type == "rent":
        try:
            prepare_rent_invoices(lease, amount)
        except ValueError as validation_error:
            db.session.rollback()
            return jsonify({"error": str(validation_error)}), 400
    elif payment_type == "deposit":
        add_lease_financial_records(lease)
        charged = sum(
            (
                entry.amount
                for entry in DepositLedgerEntry.query.filter_by(
                    lease_id=lease.id, entry_type="charge"
                ).all()
            ),
            start=0,
        )
        paid = sum(
            (
                entry.amount
                for entry in DepositLedgerEntry.query.filter_by(
                    lease_id=lease.id, entry_type="payment"
                ).all()
            ),
            start=0,
        )
        if amount > charged - paid:
            return jsonify({"error": "Payment exceeds the outstanding deposit balance"}), 400

    payment = Payment(
        lease_id=lease.id,
        amount=amount,
        currency=prop.currency,
        payment_method=payment_method,
        status=status,
        reference_code=reference_code,
        provider="manual",
        provider_reference=reference_code,
        payment_type=payment_type,
    )

    db.session.add(payment)

    try:
        if status == "Completed":
            db.session.flush()
            apply_payment_effects(payment)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "The payment reference already exists or the payment violates a database constraint"
        }), 409

    return jsonify(payment.to_dict()), 201
