"""Unit and Lease models.

Occupied/vacant is never stored. A unit is occupied when it has an active
lease whose dates cover today (see current_leases below).
"""

from datetime import date, datetime, timezone

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import synonym

from server.extensions import db

LEASE_STATUSES = ("active", "ended", "terminated")

def _now():
    return datetime.now(timezone.utc)

def _number(value):
    return None if value is None else float(value)

class Unit(db.Model):
    __tablename__ = "units"
    __table_args__ = (
        db.UniqueConstraint("property_id", "unit_number", name="uq_units_property_unit_number"),
        db.CheckConstraint("floor_number >= 1", name="ck_units_floor_number"),
        db.CheckConstraint("size IS NULL OR size > 0", name="ck_units_size_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    unit_number = db.Column(db.String(50), nullable=False)
    unit_type = db.Column(db.String(50))
    bedrooms = db.Column(db.Integer)
    bathrooms = db.Column(db.Numeric(3, 1))
    rent_amount = db.Column(db.Numeric(12, 3))
    floor_number = db.Column(db.Integer, nullable=False, default=1)
    layout = db.Column(db.String(20))
    size = db.Column(db.Numeric(12, 2))
    size_unit = db.Column(db.String(20))
    furnished = db.Column(db.Boolean, nullable=False, default=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    property = db.relationship("Property", backref="units")

    def to_dict(self, current_lease=None, is_reserved=False):
        status = (
            "occupied"
            if current_lease is not None
            else "reserved"
            if is_reserved
            else "vacant"
        )
        return {
            "id": self.id,
            "property_id": self.property_id,
            "unit_number": self.unit_number,
            "unit_type": self.unit_type,
            "bedrooms": self.bedrooms,
            "bathrooms": _number(self.bathrooms),
            "rent_amount": _number(self.rent_amount),
            "currency": self.property.currency,
            "floor_number": self.floor_number,
            "layout": self.layout,
            "size": _number(self.size),
            "size_unit": self.size_unit,
            "furnished": self.furnished,
            "rooms": [room.to_dict() for room in self.rooms],
            "photos": [
                photo.to_dict()
                for photo in sorted(self.photos, key=lambda item: (not item.is_cover, item.id))
            ],
            "is_occupied": current_lease is not None,
            "is_reserved": status == "reserved",
            "availability_status": status,
            "current_lease_id": current_lease.id if current_lease else None,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }

class Room(db.Model):
    __tablename__ = "rooms"
    __table_args__ = (
        db.CheckConstraint("size IS NULL OR size > 0", name="ck_rooms_size_positive"),
        db.CheckConstraint(
            "room_type IN ('bedroom', 'living_room', 'kitchen', 'bathroom', 'balcony', 'other')",
            name="ck_rooms_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    room_type = db.Column(db.String(30), nullable=False)
    size = db.Column(db.Numeric(12, 2))
    size_unit = db.Column(db.String(20))
    description = db.Column(db.String(1000))
    unit = db.relationship(
        "Unit",
        backref=db.backref("rooms", lazy="selectin", cascade="all, delete-orphan"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "name": self.name,
            "room_type": self.room_type,
            "size": _number(self.size),
            "size_unit": self.size_unit,
            "description": self.description,
        }

class Lease(db.Model):
    __tablename__ = "leases"
    __table_args__ = (
        db.CheckConstraint("end_date >= start_date", name="ck_leases_dates"),
        db.CheckConstraint("status IN ('active', 'ended', 'terminated')", name="ck_leases_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    monthly_rent = db.Column(db.Numeric(12, 3), nullable=False)
    deposit = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    deposit_amount = synonym("deposit")
    unit = db.relationship("Unit", backref="leases")

    @hybrid_property
    def is_active(self):
        return self.status == "active"

    @is_active.setter
    def is_active(self, value):
        self.status = "active" if value else "ended"

    @is_active.expression
    def is_active(cls):
        return cls.status == "active"

    def to_dict(self):
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "tenant_id": self.tenant_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "monthly_rent": _number(self.monthly_rent),
            "deposit": _number(self.deposit),
            "currency": self.unit.property.currency,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

def current_leases(unit_ids, today=None):
    """Map unit_id -> the active lease covering today. One query for any number of units."""
    if not unit_ids:
        return {}
    today = today or date.today()
    rows = Lease.query.filter(
        Lease.unit_id.in_(unit_ids),
        Lease.status == "active",
        Lease.start_date <= today,
        Lease.end_date >= today,
    ).all()
    return {lease.unit_id: lease for lease in rows}