from datetime import datetime, timezone

from server.extensions import db


class Tenant(db.Model):
    """A tenant record created and managed by a landlord.

    A tenant is connected to units only through leases (leases.tenant_id),
    so there is deliberately no unit_id or is_occupied column here.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        db.UniqueConstraint("landlord_id", "email", name="uq_tenant_landlord_email"),
    )

    id = db.Column(db.Integer, primary_key=True)
    # The landlord who owns this record. Every tenants endpoint filters on it.
    landlord_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    # Optional login account, so a tenant can view their own record.
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=True
    )
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "landlord_id": self.landlord_id,
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "created_at": self.created_at.isoformat(),
        }
