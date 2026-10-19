from datetime import date

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.extensions import db
from server.models import Property, User
from server.models_application import APPLICATION_STATUSES, Application
from server.models_tenant import Tenant
from server.models_unit_lease import Unit, current_leases
from server.pagination import get_pagination, pagination_metadata

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
    unit = db.session.get(Unit, application.unit_id)
    prop = db.session.get(Property, unit.property_id) if unit else None
    applicant = db.session.get(User, application.applicant_user_id)
    payload["unit"] = unit.to_dict() if unit else None
    payload["property"] = prop.to_dict() if prop else None
    payload["applicant"] = (
        {"id": applicant.id, "name": applicant.name, "email": applicant.email}
        if applicant
        else None
    )
    return payload


@applications_bp.route("", methods=["GET"])
@jwt_required()
def list_applications():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404

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
    return {
        "applications": [application_payload(application) for application in result.items],
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

    values, error = parse_application_data(request.get_json(silent=True))
    if error:
        return {"error": error}, 400
    unit = Unit.query.filter_by(id=values["unit_id"]).first()
    if not unit:
        return {"error": "Unit not found"}, 404
    if current_leases([unit.id]):
        return {"error": "This unit is not available for applications"}, 409

    pending = Application.query.filter_by(
        unit_id=unit.id,
        applicant_user_id=user.id,
        status="pending",
    ).first()
    if pending:
        return {"error": "You already have a pending application for this unit"}, 409

    application = Application(
        unit_id=unit.id,
        applicant_user_id=user.id,
        message=values["message"],
        move_in_date=values["move_in_date"],
        status="pending",
    )
    db.session.add(application)
    db.session.commit()
    return {
        "message": "Application submitted",
        "application": application_payload(application),
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
    return {"application": application_payload(application)}, 200


@applications_bp.route("/<int:application_id>", methods=["PATCH"])
@jwt_required()
def decide_application(application_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in MANAGER_ROLES:
        return {"error": "Only landlords and admins can decide applications"}, 403

    application = visible_application(user, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"status"}:
        return {"error": "Request body must contain only status"}, 400
    decision = data["status"]
    if decision not in ("approved", "declined"):
        return {"error": "status must be approved or declined"}, 400
    if application.status != "pending":
        return {"error": "Only pending applications can be decided"}, 409

    unit = db.session.get(Unit, application.unit_id)
    owner_id = db.session.get(Property, unit.property_id).owner_id
    tenant = None
    if decision == "approved":
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
    db.session.commit()

    response = {
        "message": f"Application {decision}",
        "application": application_payload(application),
    }
    if decision == "approved":
        response["tenant"] = tenant.to_dict()
        response["lease_prefill"] = {
            "tenant_id": tenant.id,
            "unit_id": unit.id,
            "start_date": application.move_in_date.isoformat(),
            "monthly_rent": (
                float(unit.rent_amount) if unit.rent_amount is not None else None
            ),
        }
    return response, 200
