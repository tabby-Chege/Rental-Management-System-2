from datetime import datetime, timezone

from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required

from server.extensions import db
from server.models import User
from server.models_application import Application, ReservationNotification
from server.pagination import get_pagination, pagination_metadata
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
    if user.role != "tenant":
        return {"error": "Notifications are available to tenant accounts"}, 403

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
    result = (
        ReservationNotification.query.filter_by(user_id=user.id)
        .order_by(
            ReservationNotification.created_at.desc(),
            ReservationNotification.id.desc(),
        )
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return {
        "notifications": [item.to_dict() for item in result.items],
        "pagination": pagination_metadata(result),
    }, 200


@notifications_bp.route("/<int:notification_id>/read", methods=["PATCH"])
@jwt_required()
def mark_notification_read(notification_id):
    user = current_user()
    if not user:
        return {"error": "User not found"}, 404
    if user.role != "tenant":
        return {"error": "Notifications are available to tenant accounts"}, 403
    notification = ReservationNotification.query.filter_by(
        id=notification_id, user_id=user.id
    ).first()
    if not notification:
        return {"error": "Notification not found"}, 404
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.session.commit()
    return {"notification": notification.to_dict()}, 200
