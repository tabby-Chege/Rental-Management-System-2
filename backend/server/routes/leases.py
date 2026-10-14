from decimal import Decimal

from flask import Blueprint, request

from server.extensions import db
from server.helpers import current_manager, error, is_id, parse_date, parse_decimal
from server.models_unit_lease import LEASE_STATUSES, Lease, Unit
from server.ownership import (
    get_owned_lease,
    get_owned_unit,
    get_tenant_for_unit,
    owned_leases_query,
)

leases_bp = Blueprint("leases", __name__, url_prefix="/api/leases")

# unit_id is not editable: to move a tenant, end this lease and create a new one.
EDITABLE = {"tenant_id", "start_date", "end_date", "monthly_rent", "deposit", "status"}


def find_overlap(unit_id, start, end, ignore_id=None):
    """An active lease on this unit whose dates overlap start..end, if there is one."""
    query = Lease.query.filter(
        Lease.unit_id == unit_id,
        Lease.status == "active",
        Lease.start_date <= end,
        Lease.end_date >= start,
    )
    if ignore_id is not None:
        query = query.filter(Lease.id != ignore_id)
    return query.first()


def overlap_error(clash):
    return error(
        f"This unit already has an active lease from {clash.start_date} to {clash.end_date}",
        409,
    )


def lease_has_payments(lease):
    """True if a payment points at this lease.

    The Payment model lives in Zack's branch. Until it is merged there is
    nothing to check, so this returns False when the model does not exist.
    """
    payment_model = db.Model.registry._class_registry.get("Payment")
    if payment_model is None:
        return False
    return (
        db.session.query(payment_model.id)
        .filter(payment_model.lease_id == lease.id)
        .first()
        is not None
    )


def read_lease_values(unit, data, current=None):
    """Validate the lease fields in data.

    For updates (current is the existing lease), fields that are not in data
    keep their current value. Returns (values, None) or (None, error_response).
    """
    values = {}

    tenant_id = data["tenant_id"] if "tenant_id" in data else (current.tenant_id if current else None)
    if not is_id(tenant_id):
        return None, error("tenant_id is required", 400)
    if not get_tenant_for_unit(unit, tenant_id):
        return None, error("Tenant not found", 404)
    values["tenant_id"] = tenant_id

    for name, label in (("start_date", "Start date"), ("end_date", "End date")):
        if name in data or current is None:
            value, message = parse_date(data.get(name), label)
            if message:
                return None, error(message, 400)
        else:
            value = getattr(current, name)
        values[name] = value
    if values["end_date"] < values["start_date"]:
        return None, error("End date cannot be before the start date", 400)

    if "monthly_rent" in data or current is None:
        rent, message = parse_decimal(data.get("monthly_rent"), "Monthly rent")
        if message:
            return None, error(message, 400)
    else:
        rent = current.monthly_rent
    values["monthly_rent"] = rent

    if "deposit" in data:
        if data["deposit"] is None or data["deposit"] == "":
            deposit = Decimal("0.00")
        else:
            deposit, message = parse_decimal(data["deposit"], "Deposit")
            if message:
                return None, error(message, 400)
    else:
        deposit = current.deposit if current else Decimal("0.00")
    values["deposit"] = deposit

    status = data["status"] if "status" in data else (current.status if current else "active")
    if status not in LEASE_STATUSES:
        return None, error("Status must be one of: " + ", ".join(LEASE_STATUSES), 400)
    values["status"] = status

    return values, None


@leases_bp.route("", methods=["GET"])
def list_leases():
    user, problem = current_manager()
    if problem:
        return problem

    query = owned_leases_query(user)

    for arg in ("tenant_id", "unit_id"):
        raw = request.args.get(arg)
        if raw is None:
            continue
        if not raw.isdigit():
            return error(f"{arg} must be a number", 400)
        query = query.filter(getattr(Lease, arg) == int(raw))

    status = request.args.get("status")
    if status:
        if status not in LEASE_STATUSES:
            return error("Status must be one of: " + ", ".join(LEASE_STATUSES), 400)
        query = query.filter(Lease.status == status)

    leases = query.order_by(Lease.start_date.desc(), Lease.id.desc()).all()
    return {"leases": [lease.to_dict() for lease in leases]}, 200


@leases_bp.route("", methods=["POST"])
def create_lease():
    user, problem = current_manager()
    if problem:
        return problem

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Request body must be valid JSON", 400)

    unit_id = data.get("unit_id")
    if not is_id(unit_id):
        return error("unit_id is required", 400)
    unit = get_owned_unit(user, unit_id)
    if not unit:
        return error("Unit not found", 404)

    values, problem = read_lease_values(unit, data)
    if problem:
        return problem

    if values["status"] == "active":
        clash = find_overlap(unit.id, values["start_date"], values["end_date"])
        if clash:
            return overlap_error(clash)

    lease = Lease(unit_id=unit.id, **values)
    db.session.add(lease)
    db.session.commit()
    return {"message": "Lease created", "lease": lease.to_dict()}, 201


@leases_bp.route("/<int:lease_id>", methods=["GET"])
def get_lease(lease_id):
    user, problem = current_manager()
    if problem:
        return problem

    lease = get_owned_lease(user, lease_id)
    if not lease:
        return error("Lease not found", 404)
    return {"lease": lease.to_dict()}, 200


@leases_bp.route("/<int:lease_id>", methods=["PUT"])
def update_lease(lease_id):
    user, problem = current_manager()
    if problem:
        return problem

    lease = get_owned_lease(user, lease_id)
    if not lease:
        return error("Lease not found", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return error("Request body must be valid JSON with at least one field", 400)

    forbidden = set(data) - EDITABLE
    if forbidden:
        return error("You cannot change: " + ", ".join(sorted(forbidden)), 403)

    unit = db.session.get(Unit, lease.unit_id)
    values, problem = read_lease_values(unit, data, current=lease)
    if problem:
        return problem

    if values["status"] == "active":
        clash = find_overlap(lease.unit_id, values["start_date"], values["end_date"], ignore_id=lease.id)
        if clash:
            return overlap_error(clash)

    for name, value in values.items():
        setattr(lease, name, value)

    db.session.commit()
    return {"message": "Lease updated", "lease": lease.to_dict()}, 200


@leases_bp.route("/<int:lease_id>", methods=["DELETE"])
def delete_lease(lease_id):
    user, problem = current_manager()
    if problem:
        return problem

    lease = get_owned_lease(user, lease_id)
    if not lease:
        return error("Lease not found", 404)

    if lease_has_payments(lease):
        return error("This lease has payments and cannot be deleted. End it instead.", 409)

    db.session.delete(lease)
    db.session.commit()
    return {"message": "Lease deleted"}, 200