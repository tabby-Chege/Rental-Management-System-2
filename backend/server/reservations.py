from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from server.extensions import db
from server.models_application import Application, ReservationNotification
from server.models_unit_lease import Lease, Unit

RESERVATION_WINDOW = timedelta(hours=1)
REMINDER_WINDOW = timedelta(minutes=15)
RESERVATION_STATUSES = ("approved", "offered")


def utc_now():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def reservation_deadline(now=None):
    return as_utc(now or utc_now()) + RESERVATION_WINDOW


def _event_key(application, notification_type, event_time):
    return (
        f"{application.id}:{notification_type}:"
        f"{as_utc(event_time).replace(microsecond=0).isoformat()}"
    )


def add_reservation_notification(
    application, notification_type, message, event_time
):
    key = _event_key(application, notification_type, event_time)
    existing = ReservationNotification.query.filter_by(event_key=key).first()
    if existing:
        return existing

    notification = ReservationNotification(
        user_id=application.applicant_user_id,
        application_id=application.id,
        notification_type=notification_type,
        event_key=key,
        message=message,
    )
    db.session.add(notification)
    return notification


def _scoped_application_query(query, unit_ids=None, user_id=None):
    if unit_ids is not None:
        ids = list(unit_ids)
        if not ids:
            return query.filter(False)
        query = query.filter(Application.unit_id.in_(ids))
    if user_id is not None:
        query = query.filter(Application.applicant_user_id == user_id)
    return query


def _local_today(property_record):
    return datetime.now(ZoneInfo(property_record.time_zone)).date()


def _expire_reservations(now, unit_ids=None, user_id=None):
    query = Application.query.filter(
        Application.status.in_(RESERVATION_STATUSES),
        Application.payment_due_at.is_not(None),
        Application.payment_due_at <= now,
    ).order_by(Application.unit_id, Application.created_at, Application.id)
    query = _scoped_application_query(query, unit_ids, user_id)
    expired_count = 0

    for application in query.with_for_update().all():
        if application.status not in RESERVATION_STATUSES:
            continue
        due_at = as_utc(application.payment_due_at)
        if due_at > now:
            continue

        application.status = "expired"
        expired_count += 1
        add_reservation_notification(
            application,
            "reservation_expired",
            "Your reservation expired because payment was not confirmed by the deadline.",
            due_at,
        )

        unit = db.session.get(Unit, application.unit_id)
        if not unit:
            continue
        today = _local_today(unit.property)
        active_lease = Lease.query.filter(
            Lease.unit_id == unit.id,
            Lease.status == "active",
            Lease.start_date <= today,
            Lease.end_date >= today,
        ).first()
        if active_lease:
            waitlisted = (
                Application.query.filter_by(
                    unit_id=unit.id,
                    status="waitlisted",
                )
                .order_by(Application.created_at, Application.id)
                .with_for_update()
                .all()
            )
            for queued in waitlisted:
                queued.status = "declined"
                queued.decision_reason = "The unit is no longer available."
                add_reservation_notification(
                    queued,
                    "waitlist_closed",
                    "The unit was leased before a waitlist offer could be made.",
                    now,
                )
            continue

        next_application = (
            Application.query.filter_by(
                unit_id=unit.id,
                status="waitlisted",
            )
            .order_by(Application.created_at, Application.id)
            .with_for_update()
            .first()
        )
        if not next_application:
            continue

        next_application.status = "offered"
        next_application.payment_due_at = reservation_deadline(now)
        add_reservation_notification(
            next_application,
            "waitlist_offer",
            "A unit became available for you from the waitlist. Confirm payment before the deadline.",
            next_application.payment_due_at,
        )

    return expired_count


def _create_deadline_reminders(now, unit_ids=None, user_id=None):
    deadline_limit = now + REMINDER_WINDOW
    query = Application.query.filter(
        Application.status.in_(RESERVATION_STATUSES),
        Application.payment_due_at > now,
        Application.payment_due_at <= deadline_limit,
    )
    query = _scoped_application_query(query, unit_ids, user_id)
    reminders = 0
    for application in query.with_for_update().all():
        notification = add_reservation_notification(
            application,
            "reservation_reminder",
            "Payment for your reservation is due within 15 minutes.",
            application.payment_due_at,
        )
        if notification.id is None:
            reminders += 1
    return reminders


def _mark_started_leases(now, unit_ids=None, user_id=None):
    query = (
        Application.query.join(Lease, Application.lease_id == Lease.id)
        .join(Unit, Lease.unit_id == Unit.id)
        .filter(
            Application.status == "paid",
            Lease.status == "active",
        )
        .order_by(Application.unit_id, Application.id)
    )
    if unit_ids is not None:
        ids = list(unit_ids)
        if not ids:
            return 0
        query = query.filter(Application.unit_id.in_(ids))
    if user_id is not None:
        query = query.filter(Application.applicant_user_id == user_id)

    started_count = 0
    for application in query.with_for_update().all():
        lease = db.session.get(Lease, application.lease_id)
        unit = db.session.get(Unit, lease.unit_id) if lease else None
        if not lease or not unit or lease.start_date > _local_today(unit.property):
            continue
        application.status = "leased"
        started_count += 1
        add_reservation_notification(
            application,
            "lease_started",
            "Your lease has started.",
            now,
        )
    return started_count


def process_reservations(now=None, unit_ids=None, user_id=None):
    current_time = as_utc(now or utc_now())
    scoped_unit_ids = None if unit_ids is None else list(unit_ids)
    expired = _expire_reservations(current_time, scoped_unit_ids, user_id)
    reminders = _create_deadline_reminders(current_time, scoped_unit_ids, user_id)
    started = _mark_started_leases(current_time, scoped_unit_ids, user_id)
    if expired or reminders or started:
        db.session.commit()
    return {
        "expired": expired,
        "reminders": reminders,
        "leases_started": started,
    }
