"""Small shared helpers for the units and leases routes."""
from datetime import date
from decimal import Decimal, InvalidOperation

from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from server.extensions import db
from server.models import User
from server.models_tenant import Tenant

MANAGER_ROLES = {"landlord", "admin"}


def error(message, status):
    return {"error": message}, status


def current_manager():
    """Return (user, None), or (None, error_response) if the caller can't manage units/leases."""
    verify_jwt_in_request()
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return None, error("User not found", 404)
    if user.role not in MANAGER_ROLES:
        return None, error("You do not have permission to access this resource", 403)
    return user, None


def current_tenant():
    """For tenant accounts: return (tenant_record, None), or (None, error_response).

    A tenant account is linked to its tenant record through Tenant.user_id
    (set by the landlord, see Luice's tenants routes).
    """
    verify_jwt_in_request()
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return None, error("User not found", 404)
    if user.role != "tenant":
        return None, error("You do not have permission to access this resource", 403)
    tenant = Tenant.query.filter_by(user_id=user.id).first()
    if not tenant:
        return None, error("No tenant record is linked to your account", 404)
    return tenant, None


def is_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def parse_date(value, label):
    """Return (date, None) or (None, message). Expects YYYY-MM-DD."""
    try:
        return date.fromisoformat(value), None
    except (TypeError, ValueError):
        return None, f"{label} must be a date in YYYY-MM-DD format"


def parse_decimal(value, label, places="0.01", maximum="99999999.99"):
    """Return (Decimal, None) or (None, message). Must be a number >= 0."""
    if isinstance(value, bool) or value is None or value == "":
        return None, f"{label} must be a number"
    try:
        amount = Decimal(str(value)).quantize(Decimal(places))
    except (InvalidOperation, ValueError):
        return None, f"{label} must be a number"
    if not amount.is_finite():
        return None, f"{label} must be a number"
    if amount < 0:
        return None, f"{label} cannot be negative"
    if amount > Decimal(maximum):
        return None, f"{label} is too large"
    return amount, None


def parse_int(value, label, maximum=50):
    """Return (int, None) or (None, message). Whole number from 0 to maximum."""
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        return None, f"{label} must be a whole number"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None, f"{label} must be a whole number"
    if number < 0 or number > maximum:
        return None, f"{label} must be between 0 and {maximum}"
    return number, None