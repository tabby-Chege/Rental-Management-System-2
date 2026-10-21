from datetime import datetime, timezone

from server.extensions import db


class TenantProfile(db.Model):
    __tablename__ = "tenant_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False
    )
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    employment_status = db.Column(db.String(40), nullable=False)
    employer = db.Column(db.String(120))
    job_title = db.Column(db.String(120))
    emergency_contact_name = db.Column(db.String(120), nullable=False)
    emergency_contact_phone = db.Column(db.String(30), nullable=False)
    emergency_contact_relationship = db.Column(db.String(80), nullable=False)
    id_type = db.Column(db.String(40))
    encrypted_id_number = db.Column(db.Text)
    previous_landlord_name = db.Column(db.String(120))
    previous_landlord_contact = db.Column(db.String(120))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self, id_number=None):
        return {
            "user_id": self.user_id,
            "full_name": self.full_name,
            "phone": self.phone,
            "employment_status": self.employment_status,
            "employer": self.employer,
            "job_title": self.job_title,
            "emergency_contact_name": self.emergency_contact_name,
            "emergency_contact_phone": self.emergency_contact_phone,
            "emergency_contact_relationship": self.emergency_contact_relationship,
            "id_type": self.id_type,
            "id_number": id_number,
            "has_id_number": self.encrypted_id_number is not None,
            "previous_landlord_name": self.previous_landlord_name,
            "previous_landlord_contact": self.previous_landlord_contact,
            "updated_at": self.updated_at.isoformat(),
        }


class TenantDocument(db.Model):
    __tablename__ = "tenant_documents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)
    object_key = db.Column(db.String(64), unique=True, nullable=False)
    content_type = db.Column(db.String(40), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    uploaded_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "content_type": self.content_type,
            "file_size": self.file_size,
            "uploaded_at": self.uploaded_at.isoformat(),
            "download_url": f"/api/tenant-documents/{self.id}",
        }


class Tenant(db.Model):
    """A landlord-scoped tenant record associated with applications and leases.

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
