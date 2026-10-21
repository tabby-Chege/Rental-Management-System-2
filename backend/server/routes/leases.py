from datetime import date

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Payment, Property, User
from server.models_tenant import Tenant
from server.models_unit_lease import LEASE_STATUSES, Lease, Unit
from server.money import parse_money
from server.occupancy import unit_occupancy
from server.pagination import get_pagination, pagination_metadata
from server.payment_service import add_lease_financial_records
from server.models_payment import RentSchedule

leases_bp = Blueprint("leases_bp", __name__, url_prefix="/api/leases")
MANAGER_ROLES = {"landlord", "admin"}
MONEY_FIELDS = {"monthly_rent", "deposit"}



def current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None



def accessible_units_query(user):
    query = Unit.query.join(Property, Unit.property_id == Property.id)
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query


def accessible_leases_query(user):
    query = Lease.query.join(Unit, Lease.unit_id == Unit.id).join(
        Property, Unit.property_id == Property.id
    )
    if user.role != "admin":
        query = query.filter(Property.owner_id == user.id)
    return query


def tenant_for_property_owner(tenant_id, owner_id):
    return Tenant.query.filter_by(id=tenant_id, landlord_id=owner_id).first()


def valid_amount(value, field, currency, *, allow_zero=False):
    _, error = parse_money(value, currency, allow_zero=allow_zero)
    return f"{field}: {error.lower()}" if error else None


def lease_json(lease):
    return lease.to_dict()


def list_leases_for_query(query):
    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    result = query.order_by(Lease.created_at.desc(), Lease.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        "leases": [lease_json(lease) for lease in result.items],
        "pagination": pagination_metadata(result),
    }, 200


@leases_bp.route("", methods=["GET"])
@jwt_required()
def list_leases():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "You do not have permission to view leases"}, 403

    query = accessible_leases_query(user)
    for field, column in (("tenant_id", Lease.tenant_id), ("unit_id", Lease.unit_id)):
        raw_value = request.args.get(field)
        if raw_value is not None:
            if not raw_value.isdecimal() or int(raw_value) < 1:
                return {"error": f"{field} must be a positive integer"}, 400
            query = query.filter(column == int(raw_value))
    status = request.args.get("status")
    if status:
        if status not in LEASE_STATUSES:
            return {"error": "status must be active, ended, or terminated"}, 400
        query = query.filter(Lease.status == status)
    return list_leases_for_query(query)


@leases_bp.route("/mine", methods=["GET"])
@jwt_required()
def list_my_leases():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role != "tenant":
        return {"error": "This route is for tenant accounts"}, 403
    tenant = Tenant.query.filter_by(user_id=user.id).first()
    query = Lease.query.filter_by(tenant_id=tenant.id) if tenant else Lease.query.filter(False)
    return list_leases_for_query(query)


@leases_bp.route("/mine/payments", methods=["GET"])
@jwt_required()
def list_my_payments():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role != "tenant":
        return {"error": "This route is for tenant accounts"}, 403
    tenant = Tenant.query.filter_by(user_id=user.id).first()
    if not tenant:
        return {"payments": []}, 200

    query = Payment.query.join(Lease, Payment.lease_id == Lease.id).filter(
        Lease.tenant_id == tenant.id
    )
    raw_lease_id = request.args.get("lease_id")
    if raw_lease_id:
        if not raw_lease_id.isdecimal() or int(raw_lease_id) < 1:
            return {"error": "lease_id must be a positive integer"}, 400
        query = query.filter(Lease.id == int(raw_lease_id))
    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    result = query.order_by(Payment.payment_date.desc(), Payment.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        "payments": [payment.to_dict() for payment in result.items],
        "pagination": pagination_metadata(result),
    }, 200


@leases_bp.route("/<int:lease_id>", methods=["GET"])
@jwt_required()
def get_lease(lease_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    lease = accessible_leases_query(user).filter(Lease.id == lease_id).first()
    if not lease and user.role == "tenant":
        tenant = Tenant.query.filter_by(user_id=user.id).first()
        if tenant:
            lease = Lease.query.filter_by(id=lease_id, tenant_id=tenant.id).first()
    if not lease:
        return {"error": "Lease not found"}, 404
    return {"lease": lease_json(lease)}, 200


def validate_lease_payload(data, *, partial=False, currency="KES"):
    if not isinstance(data, dict) or (partial and not data):
        return None, "Request body must be a JSON object with lease fields"
    allowed = {
        "tenant_id", "start_date", "end_date", "monthly_rent",
        "deposit", "deposit_amount", "status",
    }
    unknown = set(data) - allowed
    if unknown:
        return None, "Unsupported fields: " + ", ".join(sorted(unknown))

    cleaned = dict(data)
    if "deposit_amount" in cleaned:
        if "deposit" in cleaned:
            return None, "Send either deposit or deposit_amount, not both"
        cleaned["deposit"] = cleaned.pop("deposit_amount")

    for field in ("tenant_id",):
        if field in cleaned and (
            isinstance(cleaned[field], bool)
            or not isinstance(cleaned[field], int)
            or cleaned[field] < 1
        ):
            return None, f"{field} must be a positive integer"
    for field in ("start_date", "end_date"):
        if field in cleaned:
            try:
                if not isinstance(cleaned[field], str):
                    raise ValueError
                cleaned[field] = date.fromisoformat(cleaned[field])
            except ValueError:
                return None, f"{field} must use YYYY-MM-DD format"
    for field in MONEY_FIELDS:
        if field in cleaned:
            message = valid_amount(
                cleaned[field], field, currency, allow_zero=(field == "deposit")
            )
            if message:
                return None, message
            cleaned[field] = parse_money(
                cleaned[field], currency, allow_zero=(field == "deposit")
            )[0]
    if "status" in cleaned and cleaned["status"] not in LEASE_STATUSES:
        return None, "status must be active, ended, or terminated"
    if not partial:
        required = {"tenant_id", "start_date", "end_date", "monthly_rent"}
        missing = required - cleaned.keys()
        if missing:
            return None, "Missing required lease fields: " + ", ".join(sorted(missing))
        cleaned.setdefault("deposit", 0)
        cleaned.setdefault("status", "active")
    if "start_date" in cleaned and "end_date" in cleaned:
        if cleaned["end_date"] <= cleaned["start_date"]:
            return None, "End date must occur after the start date"
    return cleaned, None


def lease_conflicts(unit_id, start_date, end_date, exclude_id=None):
    query = Lease.query.filter(
        Lease.unit_id == unit_id,
        Lease.status == "active",
        Lease.start_date <= end_date,
        Lease.end_date >= start_date,
    )
    if exclude_id is not None:
        query = query.filter(Lease.id != exclude_id)
    return query.first() is not None


@leases_bp.route("", methods=["POST"])
@jwt_required()
def create_lease():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can create leases"}, 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be valid JSON"}, 400
    unit_id = data.get("unit_id")
    if isinstance(unit_id, bool) or not isinstance(unit_id, int) or unit_id < 1:
        return {"error": "unit_id must be a positive integer"}, 400
    unit = accessible_units_query(user).filter(Unit.id == unit_id).first()
    if not unit:
        return {"error": "Unit not found"}, 404
    prop = db.session.get(Property, unit.property_id)
    occupancy = unit_occupancy([unit.id])[unit.id]
    if occupancy["is_reserved"]:
        return {
            "error": "Confirm the reservation payment before creating a lease"
        }, 409
    payload = {key: value for key, value in data.items() if key != "unit_id"}
    cleaned, error = validate_lease_payload(payload, currency=prop.currency)
    if error:
        return {"error": error}, 400
    tenant = tenant_for_property_owner(cleaned["tenant_id"], prop.owner_id)
    if not tenant:
        return {"error": "Tenant not found for this property owner"}, 404
    if cleaned["status"] == "active" and lease_conflicts(
        unit.id, cleaned["start_date"], cleaned["end_date"]
    ):
        return {"error": "Unit is already leased during this timeframe"}, 409

    lease = Lease(unit_id=unit.id, **cleaned)
    db.session.add(lease)
    try:
        db.session.flush()
        add_lease_financial_records(lease)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "Lease conflicts with existing records"}, 409
    serialized = lease_json(lease)
    return {"lease": serialized, **serialized}, 201


@leases_bp.route("/<int:lease_id>", methods=["PUT"])
@jwt_required()
def update_lease(lease_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can update leases"}, 403
    lease = accessible_leases_query(user).filter(Lease.id == lease_id).first()
    if not lease:
        return {"error": "Lease not found"}, 404
    cleaned, error = validate_lease_payload(
        request.get_json(silent=True),
        partial=True,
        currency=lease.unit.property.currency,
    )
    if error:
        return {"error": error}, 400

    tenant_id = cleaned.get("tenant_id", lease.tenant_id)
    unit = db.session.get(Unit, lease.unit_id)
    prop = db.session.get(Property, unit.property_id)
    tenant = tenant_for_property_owner(tenant_id, prop.owner_id)
    if not tenant:
        return {"error": "Tenant not found for this property owner"}, 404
    start_date = cleaned.get("start_date", lease.start_date)
    end_date = cleaned.get("end_date", lease.end_date)
    if end_date <= start_date:
        return {"error": "End date must occur after the start date"}, 400
    status = cleaned.get("status", lease.status)
    if status == "active" and lease_conflicts(
        lease.unit_id, start_date, end_date, exclude_id=lease.id
    ):
        return {"error": "Unit is already leased during this timeframe"}, 409

    for field, value in cleaned.items():
        setattr(lease, field, value)
    if status == "active":
        add_lease_financial_records(lease)
    else:
        schedule = RentSchedule.query.filter_by(lease_id=lease.id).first()
        if schedule:
            schedule.active = False
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "Lease conflicts with existing records"}, 409
    serialized = lease_json(lease)
    return {"lease": serialized, **serialized}, 200


@leases_bp.route("/<int:lease_id>", methods=["DELETE"])
@jwt_required()
def terminate_lease(lease_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can end leases"}, 403
    lease = accessible_leases_query(user).filter(Lease.id == lease_id).first()
    if not lease:
        return {"error": "Lease not found"}, 404
    lease.status = "terminated"
    db.session.commit()
    return {"message": "Lease terminated successfully"}, 200
