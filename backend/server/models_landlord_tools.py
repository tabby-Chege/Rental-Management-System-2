from datetime import datetime, timezone

from server.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class MaintenanceRequest(db.Model):
    __tablename__ = "maintenance_requests"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('submitted', 'in_progress', 'resolved', 'closed')",
            name="ck_maintenance_requests_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id"), nullable=False, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.String(5000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="submitted", server_default="submitted")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self, photos=None, property_name=None, unit_number=None):
        return {
            "id": self.id,
            "lease_id": self.lease_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "property_name": property_name,
            "unit_number": unit_number,
            "photos": [photo.to_dict() for photo in (photos or [])],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class MaintenancePhoto(db.Model):
    __tablename__ = "maintenance_photos"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer, db.ForeignKey("maintenance_requests.id"), nullable=False, index=True
    )
    object_key = db.Column(db.String(64), unique=True, nullable=False)
    content_type = db.Column(db.String(40), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "content_type": self.content_type,
            "file_size": self.file_size,
            "uploaded_at": self.uploaded_at.isoformat(),
            "download_url": f"/api/maintenance/photos/{self.id}",
        }


class LeaseDocument(db.Model):
    __tablename__ = "lease_documents"

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id"), nullable=False, index=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename = db.Column(db.String(180), nullable=False)
    object_key = db.Column(db.String(64), unique=True, nullable=False)
    content_type = db.Column(db.String(40), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "lease_id": self.lease_id,
            "filename": self.filename,
            "content_type": self.content_type,
            "file_size": self.file_size,
            "uploaded_at": self.uploaded_at.isoformat(),
            "download_url": f"/api/lease-documents/{self.id}",
        }
