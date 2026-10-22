from datetime import datetime, timezone

from server.extensions import db

APPLICATION_STATUSES = (
    "pending",
    "approved",
    "declined",
    "waitlisted",
    "offered",
    "expired",
    "paid",
    "leased",
)
RESERVED_APPLICATION_STATUSES = ("approved", "offered", "paid")


class Application(db.Model):
    __tablename__ = "applications"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'declined', 'waitlisted', 'offered', 'expired', 'paid', 'leased')",
            name="ck_applications_status",
        ),
        db.Index(
            "uq_applications_active_reservation_unit",
            "unit_id",
            unique=True,
            sqlite_where=db.text("status IN ('approved', 'offered', 'paid')"),
            postgresql_where=db.text("status IN ('approved', 'offered', 'paid')"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(
        db.Integer, db.ForeignKey("units.id"), nullable=False, index=True
    )
    applicant_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=True, index=True
    )
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id"), nullable=True)
    message = db.Column(db.Text, nullable=True)
    move_in_date = db.Column(db.Date, nullable=False)
    lease_end_date = db.Column(db.Date, nullable=True)
    payment_due_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    profile_snapshot = db.Column(
        db.JSON, nullable=False, default=dict, server_default=db.text("'{}'")
    )
    decision_reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        payment_due_at = self.payment_due_at
        if payment_due_at:
            payment_due_at = (
                payment_due_at.replace(tzinfo=timezone.utc)
                if payment_due_at.tzinfo is None
                else payment_due_at.astimezone(timezone.utc)
            )
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "applicant_user_id": self.applicant_user_id,
            "tenant_id": self.tenant_id,
            "lease_id": self.lease_id,
            "message": self.message,
            "move_in_date": self.move_in_date.isoformat(),
            "lease_end_date": (
                self.lease_end_date.isoformat() if self.lease_end_date else None
            ),
            "payment_due_at": (
                payment_due_at.isoformat() if payment_due_at else None
            ),
            "decision_reason": self.decision_reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class ReservationNotification(db.Model):
    __tablename__ = "reservation_notifications"
    __table_args__ = (
        db.Index(
            "ix_reservation_notifications_user_created",
            "user_id",
            "created_at",
        ),
        db.UniqueConstraint("event_key", name="uq_reservation_notifications_event"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    application_id = db.Column(
        db.Integer, db.ForeignKey("applications.id"), nullable=False
    )
    notification_type = db.Column(db.String(32), nullable=False)
    event_key = db.Column(db.String(180), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    read_at = db.Column(db.DateTime(timezone=True))

    def to_dict(self):
        return {
            "id": self.id,
            "application_id": self.application_id,
            "notification_type": self.notification_type,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }
