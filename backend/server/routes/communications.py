from datetime import datetime, timezone

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Property, User
from server.models_application import Application
from server.models_communications import PropertyConversation, PropertyMessage
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit
from server.pagination import get_pagination, pagination_metadata

communications_bp = Blueprint(
    "communications", __name__, url_prefix="/api/conversations"
)
MAX_MESSAGE_LENGTH = 5000


def current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def visible_conversation(user, conversation_id):
    query = PropertyConversation.query.filter_by(id=conversation_id)
    if user.role == "tenant":
        return query.filter_by(tenant_user_id=user.id).first()
    if user.role == "landlord":
        return (
            query.join(Property)
            .filter(Property.owner_id == user.id)
            .first()
        )
    if user.role == "admin":
        return query.first()
    return None


def conversation_payload(conversation, user):
    property_record = db.session.get(Property, conversation.property_id)
    other_user_id = (
        property_record.owner_id
        if user.role == "tenant"
        else conversation.tenant_user_id
    )
    other_user = db.session.get(User, other_user_id)
    latest_message = (
        PropertyMessage.query.filter_by(conversation_id=conversation.id)
        .order_by(PropertyMessage.created_at.desc(), PropertyMessage.id.desc())
        .first()
    )
    read_at = (
        conversation.tenant_read_at
        if user.role == "tenant"
        else conversation.landlord_read_at
    )
    unread_query = PropertyMessage.query.filter(
        PropertyMessage.conversation_id == conversation.id,
        PropertyMessage.sender_user_id != user.id,
    )
    if read_at:
        unread_query = unread_query.filter(PropertyMessage.created_at > read_at)
    lease_id = None
    if conversation.application_id:
        application = db.session.get(Application, conversation.application_id)
        lease_id = application.lease_id if application else None
    if lease_id is None and conversation.unit_id:
        tenant = Tenant.query.filter_by(user_id=conversation.tenant_user_id).first()
        lease = (
            Lease.query.filter_by(unit_id=conversation.unit_id, tenant_id=tenant.id)
            .order_by(Lease.id.desc())
            .first()
            if tenant
            else None
        )
        lease_id = lease.id if lease else None
    return {
        "id": conversation.id,
        "property_id": conversation.property_id,
        "property": (
            {
                "id": property_record.id,
                "name": property_record.name,
                "city": property_record.city,
            }
            if property_record
            else None
        ),
        "other_party": (
            {
                "id": other_user.id,
                "name": other_user.name,
                "role": other_user.role,
            }
            if other_user
            else None
        ),
        "unit_id": conversation.unit_id,
        "application_id": conversation.application_id,
        "lease_id": lease_id,
        "unit": (
            {
                "id": unit.id,
                "unit_number": unit.unit_number,
            }
            if conversation.unit_id
            and (unit := db.session.get(Unit, conversation.unit_id))
            else None
        ),
        "unread_count": unread_query.count(),
        "latest_message": latest_message.to_dict() if latest_message else None,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


def parse_message(data):
    if not isinstance(data, dict) or set(data) != {"body"}:
        return None, "Request body must contain only a message body"
    body = data.get("body")
    if not isinstance(body, str):
        return None, "Message body must be text"
    body = body.strip()
    if not body:
        return None, "Message body cannot be empty"
    if len(body) > MAX_MESSAGE_LENGTH:
        return None, f"Message body must be {MAX_MESSAGE_LENGTH} characters or fewer"
    return body, None


@communications_bp.route("", methods=["GET"])
@jwt_required()
def list_conversations():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role == "tenant":
        query = PropertyConversation.query.filter_by(tenant_user_id=user.id)
    elif user.role == "landlord":
        query = (
            PropertyConversation.query.join(Property)
            .filter(Property.owner_id == user.id)
        )
    elif user.role == "admin":
        query = PropertyConversation.query
    else:
        return {"error": "Only tenants and landlords can view conversations"}, 403

    conversations = query.order_by(
        PropertyConversation.updated_at.desc(), PropertyConversation.id.desc()
    ).all()
    return {
        "conversations": [
            conversation_payload(conversation, user)
            for conversation in conversations
        ]
    }, 200


@communications_bp.route("", methods=["POST"])
@jwt_required()
def start_conversation():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Request body must be a JSON object"}, 400
    allowed = {"property_id", "body", "unit_id", "application_id"}
    if user.role in {"landlord", "admin"}:
        allowed.add("tenant_user_id")
    if set(data) - allowed or not {"property_id", "body"}.issubset(data):
        return {"error": "Request contains missing or unsupported conversation fields"}, 400
    property_id = data.get("property_id")
    if isinstance(property_id, bool) or not isinstance(property_id, int) or property_id < 1:
        return {"error": "property_id must be a positive integer"}, 400
    body, problem = parse_message({"body": data.get("body")})
    if problem:
        return {"error": problem}, 400
    property_record = db.session.get(Property, property_id)
    if not property_record:
        return {"error": "Property not found"}, 404
    if user.role not in {"tenant", "landlord", "admin"}:
        return {"error": "Only tenants and landlords can start conversations"}, 403

    unit_id = data.get("unit_id")
    application_id = data.get("application_id")
    if unit_id is not None and (
        isinstance(unit_id, bool) or not isinstance(unit_id, int) or unit_id < 1
    ):
        return {"error": "unit_id must be a positive integer"}, 400
    if application_id is not None and (
        isinstance(application_id, bool)
        or not isinstance(application_id, int)
        or application_id < 1
    ):
        return {"error": "application_id must be a positive integer"}, 400

    unit = db.session.get(Unit, unit_id) if unit_id else None
    if unit_id and (not unit or unit.property_id != property_record.id):
        return {"error": "Unit not found for this property"}, 404
    tenant_user_id = user.id
    if user.role in {"landlord", "admin"}:
        tenant_user_id = data.get("tenant_user_id")
        if isinstance(tenant_user_id, bool) or not isinstance(tenant_user_id, int):
            return {"error": "tenant_user_id must identify a tenant"}, 400
        tenant_user = db.session.get(User, tenant_user_id)
        if not tenant_user or tenant_user.role != "tenant":
            return {"error": "Tenant not found"}, 404
        if user.role == "landlord" and property_record.owner_id != user.id:
            return {"error": "Property not found"}, 404

    if application_id:
        application = db.session.get(Application, application_id)
        if (
            not application
            or application.applicant_user_id != tenant_user_id
            or (unit_id and application.unit_id != unit_id)
        ):
            return {"error": "Application not found for this tenant and unit"}, 404
        app_unit = db.session.get(Unit, application.unit_id)
        if not app_unit or app_unit.property_id != property_record.id:
            return {"error": "Application not found for this property"}, 404
        unit_id = application.unit_id
    elif user.role == "tenant" and data.get("tenant_user_id") is not None:
        return {"error": "Tenants cannot select another conversation participant"}, 400

    if user.role == "tenant" and property_record.owner_id == user.id:
        return {"error": "You cannot message yourself about this property"}, 400

    context_key = (
        f"application:{application_id}"
        if application_id
        else f"unit:{unit_id}" if unit_id else "property"
    )
    conversation = PropertyConversation.query.filter_by(
        property_id=property_record.id,
        tenant_user_id=tenant_user_id,
        context_key=context_key,
    ).first()
    if not conversation:
        conversation = PropertyConversation(
            property_id=property_record.id,
            tenant_user_id=tenant_user_id,
            unit_id=unit_id,
            application_id=application_id,
            context_key=context_key,
        )
        db.session.add(conversation)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            conversation = PropertyConversation.query.filter_by(
                property_id=property_record.id,
                tenant_user_id=tenant_user_id,
                context_key=context_key,
            ).first()
            if not conversation:
                return {"error": "Could not start the property conversation"}, 409

    message = PropertyMessage(
        conversation_id=conversation.id,
        sender_user_id=user.id,
        body=body,
    )
    conversation.updated_at = datetime.now(timezone.utc)
    db.session.add(message)
    db.session.commit()
    return {
        "conversation": conversation_payload(conversation, user),
        "message": message.to_dict(),
    }, 201


@communications_bp.route("/<int:conversation_id>/messages", methods=["GET"])
@jwt_required()
def list_messages(conversation_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    conversation = visible_conversation(user, conversation_id)
    if not conversation:
        return {"error": "Conversation not found"}, 404
    pagination, problem = get_pagination()
    if problem:
        return {"error": problem}, 400
    page, per_page = pagination
    result = (
        PropertyMessage.query.filter_by(conversation_id=conversation.id)
        .order_by(PropertyMessage.created_at, PropertyMessage.id)
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    read_field = "tenant_read_at" if user.role == "tenant" else "landlord_read_at"
    setattr(conversation, read_field, datetime.now(timezone.utc))
    db.session.commit()
    return {
        "conversation": conversation_payload(conversation, user),
        "messages": [message.to_dict() for message in result.items],
        "pagination": pagination_metadata(result),
    }, 200


@communications_bp.route("/<int:conversation_id>/messages", methods=["POST"])
@jwt_required()
def send_message(conversation_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    conversation = visible_conversation(user, conversation_id)
    if not conversation:
        return {"error": "Conversation not found"}, 404
    body, problem = parse_message(request.get_json(silent=True))
    if problem:
        return {"error": problem}, 400

    message = PropertyMessage(
        conversation_id=conversation.id,
        sender_user_id=user.id,
        body=body,
    )
    conversation.updated_at = datetime.now(timezone.utc)
    db.session.add(message)
    db.session.commit()
    return {
        "conversation": conversation_payload(conversation, user),
        "message": message.to_dict(),
    }, 201
