from datetime import datetime, timezone
from server.extensions import bcrypt, db
from sqlalchemy.orm import synonym


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(20), nullable=False, default="tenant")
    google_sub = db.Column(db.String(255), unique=True, nullable=True)
    totp_secret = db.Column(db.Text, nullable=True)
    totp_pending_secret = db.Column(db.Text, nullable=True)
    totp_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    totp_last_counter = db.Column(db.Integer, nullable=True)
    mfa_phone = db.Column(db.String(20), nullable=True)
    mfa_phone_verified = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )
    failed_login_attempts = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    login_attempt_window_started_at = db.Column(db.DateTime(timezone=True))
    locked_until = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


class RevokedToken(db.Model):
    __tablename__ = "revoked_tokens"

    jti = db.Column(db.String(36), primary_key=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        db.CheckConstraint(
            "payment_type IN ('reservation', 'rent', 'deposit', 'other')",
            name="ck_payments_payment_type",
        ),
        db.Index(
            "uq_payments_provider_reference",
            "provider",
            "provider_reference",
            unique=True,
            sqlite_where=db.text("provider_reference IS NOT NULL"),
            postgresql_where=db.text("provider_reference IS NOT NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 3), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="KES", server_default="KES")
    payment_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    payment_method = db.Column(db.String(50), nullable=False)  # M-Pesa, Bank Transfer, Cash
    status = db.Column(db.String(20), default='Completed', nullable=False)  # Completed, Pending, Failed
    reference_code = db.Column(db.String(100), unique=True, nullable=True)  # Transaction reference
    provider = db.Column(db.String(40), nullable=False, default="manual", server_default="manual")
    provider_reference = db.Column(db.String(160), nullable=True)
    payment_type = db.Column(db.String(20), nullable=False, default="rent", server_default="rent")

    lease = db.relationship(
        "Lease",
        backref=db.backref("payments", lazy=True, cascade="all, delete-orphan"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "lease_id": self.lease_id,
            "amount": float(self.amount) if self.amount is not None else None,
            "currency": self.currency,
            "payment_date": self.payment_date.isoformat(),
            "payment_method": self.payment_method,
            "status": self.status,
            "reference_code": self.reference_code,
            "provider": self.provider,
            "provider_reference": self.provider_reference,
            "payment_type": self.payment_type,
        }


class Property(db.Model):
    __tablename__ = "properties"
    __table_args__ = (
        db.CheckConstraint(
            "rental_type IN ('multi_unit', 'whole_property')",
            name="ck_properties_rental_type",
        ),
        db.CheckConstraint(
            "subtype IN ('apartment_block', 'bungalow', 'maisonette', 'villa', 'townhouse', 'commercial')",
            name="ck_properties_subtype",
        ),
        db.CheckConstraint("floors >= 1", name="ck_properties_floors"),
        db.CheckConstraint(
            "reservation_hold_hours BETWEEN 1 AND 720",
            name="ck_properties_reservation_hold_hours",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    address_line = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(2), nullable=False, default="KE")
    region = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    time_zone = db.Column(db.String(64), nullable=False, default="Africa/Nairobi")
    currency = db.Column(db.String(3), nullable=False, default="KES")
    rental_type = db.Column(db.String(20), nullable=False, default="multi_unit")
    subtype = db.Column(db.String(30), nullable=False, default="apartment_block")
    floors = db.Column(db.Integer, nullable=False, default=1)
    # Retained for existing databases; the reservation service uses a fixed window.
    reservation_hold_hours = db.Column(
        db.Integer, nullable=False, default=48, server_default="48"
    )
    description = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Keep existing API clients and ORM fixtures working while the address
    # contract moves to internationally neutral field names.
    address = synonym("address_line")
    state = synonym("region")
    zip_code = synonym("postal_code")

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "address_line": self.address_line,
            "city": self.city,
            "country": self.country,
            "region": self.region,
            "postal_code": self.postal_code,
            "time_zone": self.time_zone,
            "currency": self.currency,
            "rental_type": self.rental_type,
            "subtype": self.subtype,
            "floors": self.floors,
            "photos": [
                photo.to_dict()
                for photo in sorted(self.photos, key=lambda item: (not item.is_cover, item.id))
            ],
            "address": self.address_line,
            "state": self.region,
            "zip_code": self.postal_code,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }