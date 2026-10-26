from datetime import datetime, timezone

from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.extensions import db
from server.models import Property, User
from server.models_application import Application, ReservationNotification
from server.models_communications import PropertyConversation, PropertyMessage
from server.pagination import get_pagination
from server.reservations import process_reservations

notifications_bp = Blueprint(
    "notifications", __name__, url_prefix="/api/notifications"
)


def current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


@notifications_bp.route("", methods=["GET"])
@jwt_required()
def list_notifications():
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role not in {"tenant", "landlord"}:
        return {"error": "Notifications are available to tenant and landlord accounts"}, 403

    if user.role == "tenant":
        unit_ids = (
            db.session.query(Application.unit_id)
            .filter(Application.applicant_user_id == user.id)
            .distinct()
        )
        process_reservations(unit_ids=(unit_id for (unit_id,) in unit_ids))
    pagination, error = get_pagination()
    if error:
        return {"error": error}, 400
    page, per_page = pagination
    notifications = []
    if user.role == "tenant":
        result = (
            ReservationNotification.query.filter_by(user_id=user.id)
            .order_by(
                ReservationNotification.created_at.desc(),
                ReservationNotification.id.desc(),
            )
            .all()
        )
        notifications.extend(item.to_dict() for item in result)
    conversations = (
        PropertyConversation.query.filter_by(tenant_user_id=user.id)
        if user.role == "tenant"
        else PropertyConversation.query.join(Property)
        .filter(Property.owner_id == user.id)
    ).all()
    for conversation in conversations:
        read_at = (
            conversation.tenant_read_at
            if user.role == "tenant"
            else conversation.landlord_read_at
        )
        messages = PropertyMessage.query.filter(
            PropertyMessage.conversation_id == conversation.id,
            PropertyMessage.sender_user_id != user.id,
        )
        if read_at:
            messages = messages.filter(PropertyMessage.created_at > read_at)
        message = messages.order_by(
            PropertyMessage.created_at.desc(), PropertyMessage.id.desc()
        ).first()
        if not message:
            continue
        notifications.append(
            {
                "id": f"message-{conversation.id}",
                "notification_type": "message",
                "conversation_id": conversation.id,
                "application_id": conversation.application_id,
                "message": message.body,
                "created_at": message.created_at.isoformat(),
                "read_at": None,
            }
        )
    notifications.sort(key=lambda item: item["created_at"], reverse=True)
    start = (page - 1) * per_page
    page_items = notifications[start : start + per_page]
    return {
        "notifications": page_items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": len(notifications),
            "pages": (len(notifications) + per_page - 1) // per_page,
        },
    }, 200


@notifications_bp.route("/<string:notification_id>/read", methods=["PATCH"])
@jwt_required()
def mark_notification_read(notification_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if notification_id.startswith("message-"):
        if user.role not in {"tenant", "landlord"}:
            return {"error": "Notifications are available to tenant and landlord accounts"}, 403
        try:
            conversation_id = int(notification_id.removeprefix("message-"))
        except ValueError:
            return {"error": "Notification not found"}, 404
        conversation_query = PropertyConversation.query.filter_by(
            id=conversation_id
        )
        if user.role == "tenant":
            conversation_query = conversation_query.filter_by(
                tenant_user_id=user.id
            )
        else:
            conversation_query = conversation_query.join(Property).filter(
                Property.owner_id == user.id
            )
        conversation = conversation_query.first()
        if not conversation:
            return {"error": "Notification not found"}, 404
        read_at = datetime.now(timezone.utc)
        if user.role == "tenant":
            conversation.tenant_read_at = read_at
        else:
            conversation.landlord_read_at = read_at
        db.session.commit()
        return {
            "notification": {
                "id": notification_id,
                "notification_type": "message",
                "conversation_id": conversation.id,
                "read_at": read_at.isoformat(),
            }
        }, 200
    if user.role != "tenant":
        return {"error": "Reservation notifications are available to tenant accounts"}, 403
    try:
        reservation_id = int(notification_id)
    except ValueError:
        return {"error": "Notification not found"}, 404
    notification = ReservationNotification.query.filter_by(
        id=reservation_id, user_id=user.id
    ).first()
    if not notification:
        return {"error": "Notification not found"}, 404
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.session.commit()
    return {"notification": notification.to_dict()}, 200
