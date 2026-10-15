"""Unit and Lease models.

Occupied/vacant is never stored. A unit is occupied when it has an active
lease whose dates cover today (see current_leases below).
"""

from datetime import date, datetime, timezone

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
    )

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True)
    unit_number = db.Column(db.String(50), nullable=False)
    bedrooms = db.Column(db.Integer)
    bathrooms = db.Column(db.Numeric(3, 1))
    rent_amount = db.Column(db.Numeric(10, 2))
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self, current_lease=None):
        return {
            "id": self.id,
            "property_id": self.property_id,
            "unit_number": self.unit_number,
            "bedrooms": self.bedrooms,
            "bathrooms": _number(self.bathrooms),
            "rent_amount": _number(self.rent_amount),
            "is_occupied": current_lease is not None,
            "current_lease_id": current_lease.id if current_lease else None,
            "created_at": self.created_at.isoformat(),
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
    monthly_rent = db.Column(db.Numeric(10, 2), nullable=False)
    deposit = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "tenant_id": self.tenant_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "monthly_rent": _number(self.monthly_rent),
            "deposit": _number(self.deposit),
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