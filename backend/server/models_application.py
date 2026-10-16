from datetime import datetime, timezone

from server.extensions import db

APPLICATION_STATUSES = ("pending", "approved", "declined")


class Application(db.Model):
    __tablename__ = "applications"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'declined')",
            name="ck_applications_status",
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
    message = db.Column(db.Text, nullable=True)
    move_in_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "applicant_user_id": self.applicant_user_id,
            "tenant_id": self.tenant_id,
            "message": self.message,
            "move_in_date": self.move_in_date.isoformat(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
