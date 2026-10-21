from datetime import datetime, timezone

from sqlalchemy import Index, text

from server.extensions import db


class PropertyPhoto(db.Model):
    __tablename__ = "property_photos"
    __table_args__ = (
        db.CheckConstraint(
            "(property_id IS NOT NULL AND unit_id IS NULL) OR "
            "(property_id IS NULL AND unit_id IS NOT NULL)",
            name="ck_property_photos_single_listing",
        ),
        db.CheckConstraint(
            "room_id IS NULL OR unit_id IS NOT NULL",
            name="ck_property_photos_room_requires_unit",
        ),
        Index(
            "uq_property_photos_property_cover",
            "property_id",
            unique=True,
            sqlite_where=text("is_cover = 1 AND property_id IS NOT NULL"),
            postgresql_where=text("is_cover IS TRUE AND property_id IS NOT NULL"),
        ),
        Index(
            "uq_property_photos_unit_cover",
            "unit_id",
            unique=True,
            sqlite_where=text("is_cover = 1 AND unit_id IS NOT NULL"),
            postgresql_where=text("is_cover IS TRUE AND unit_id IS NOT NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(
        db.Integer, db.ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    unit_id = db.Column(
        db.Integer, db.ForeignKey("units.id", ondelete="CASCADE"), index=True
    )
    room_id = db.Column(
        db.Integer, db.ForeignKey("rooms.id", ondelete="SET NULL"), index=True
    )
    object_key = db.Column(db.String(64), unique=True, nullable=False)
    content_type = db.Column(db.String(20), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    is_cover = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    property = db.relationship(
        "Property",
        backref=db.backref("photos", lazy="selectin", cascade="all, delete-orphan"),
    )
    unit = db.relationship(
        "Unit",
        backref=db.backref("photos", lazy="selectin", cascade="all, delete-orphan"),
    )
    room = db.relationship("Room")

    def to_dict(self):
        return {
            "id": self.id,
            "property_id": self.property_id,
            "unit_id": self.unit_id,
            "room_id": self.room_id,
            "content_type": self.content_type,
            "file_size": self.file_size,
            "is_cover": self.is_cover,
            "url": f"/api/public/photos/{self.id}",
            "created_at": self.created_at.isoformat(),
        }


class ListingReport(db.Model):
    __tablename__ = "listing_reports"
    __table_args__ = (
        db.CheckConstraint(
            "(property_id IS NOT NULL AND unit_id IS NULL) OR "
            "(property_id IS NULL AND unit_id IS NOT NULL)",
            name="ck_listing_reports_single_listing",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    property_id = db.Column(
        db.Integer, db.ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    unit_id = db.Column(
        db.Integer, db.ForeignKey("units.id", ondelete="CASCADE"), index=True
    )
    reason = db.Column(db.String(40), nullable=False)
    details = db.Column(db.String(1000))
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "property_id": self.property_id,
            "unit_id": self.unit_id,
            "reason": self.reason,
            "details": self.details,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
