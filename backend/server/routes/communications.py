from datetime import datetime, timezone

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from server.extensions import db
from server.models import Property, User
from server.models_communications import PropertyConversation, PropertyMessage
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
    if user.role != "tenant":
        return {"error": "Only tenants can start property conversations"}, 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"property_id", "body"}:
        return {"error": "Request body must contain property_id and body"}, 400
    property_id = data.get("property_id")
    if isinstance(property_id, bool) or not isinstance(property_id, int) or property_id < 1:
        return {"error": "property_id must be a positive integer"}, 400
    body, problem = parse_message({"body": data.get("body")})
    if problem:
        return {"error": problem}, 400
    property_record = db.session.get(Property, property_id)
    if not property_record:
        return {"error": "Property not found"}, 404

    conversation = PropertyConversation.query.filter_by(
        property_id=property_record.id, tenant_user_id=user.id
    ).first()
    if not conversation:
        conversation = PropertyConversation(
            property_id=property_record.id,
            tenant_user_id=user.id,
        )
        db.session.add(conversation)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            conversation = PropertyConversation.query.filter_by(
                property_id=property_record.id, tenant_user_id=user.id
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
