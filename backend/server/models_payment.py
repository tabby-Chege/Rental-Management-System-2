from datetime import datetime, timezone

from server.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class PaymentAttempt(db.Model):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        db.CheckConstraint(
            "lease_id IS NOT NULL OR application_id IS NOT NULL",
            name="ck_payment_attempts_target",
        ),
        db.UniqueConstraint(
            "idempotency_key", name="uq_payment_attempts_idempotency_key"
        ),
        db.Index(
            "uq_payment_attempts_provider_reference",
            "provider",
            "provider_reference",
            unique=True,
            sqlite_where=db.text("provider_reference IS NOT NULL"),
            postgresql_where=db.text("provider_reference IS NOT NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id"), nullable=True, index=True)
    application_id = db.Column(
        db.Integer, db.ForeignKey("applications.id"), nullable=True, index=True
    )
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=True)
    idempotency_key = db.Column(db.String(80), nullable=False)
    provider = db.Column(db.String(40), nullable=False)
    provider_reference = db.Column(db.String(160), nullable=True)
    amount = db.Column(db.Numeric(12, 3), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    payment_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    checkout_url = db.Column(db.String(2048), nullable=True)
    customer_email = db.Column(db.String(254), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    lease_end_date = db.Column(db.Date, nullable=True)
    provider_data = db.Column(db.JSON, nullable=False, default=dict, server_default=db.text("'{}'"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "provider_reference": self.provider_reference,
            "amount": float(self.amount),
            "currency": self.currency,
            "payment_type": self.payment_type,
            "status": self.status,
            "checkout_url": self.checkout_url,
            "lease_id": self.lease_id,
            "application_id": self.application_id,
            "payment_id": self.payment_id,
            "instructions": (
                (self.provider_data or {}).get("instructions")
                if self.provider == "bank_transfer"
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class RentSchedule(db.Model):
    __tablename__ = "rent_schedules"
    __table_args__ = (
        db.CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_rent_schedules_due_day"),
        db.CheckConstraint("amount > 0", name="ck_rent_schedules_amount"),
        db.UniqueConstraint("lease_id", name="uq_rent_schedules_lease_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(
        db.Integer, db.ForeignKey("leases.id"), nullable=False
    )
    amount = db.Column(db.Numeric(12, 3), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    due_day = db.Column(db.Integer, nullable=False)
    next_due_date = db.Column(db.Date, nullable=False, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class RentInvoice(db.Model):
    __tablename__ = "rent_invoices"
    __table_args__ = (
        db.UniqueConstraint("lease_id", "due_date", name="uq_rent_invoices_lease_due"),
        db.CheckConstraint("amount > 0", name="ck_rent_invoices_amount"),
        db.CheckConstraint("amount_paid >= 0", name="ck_rent_invoices_amount_paid"),
        db.CheckConstraint(
            "status IN ('open', 'partial', 'paid', 'overdue')",
            name="ck_rent_invoices_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id"), nullable=False, index=True)
    due_date = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 3), nullable=False)
    amount_paid = db.Column(db.Numeric(12, 3), nullable=False, default=0, server_default="0")
    currency = db.Column(db.String(3), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", server_default="open")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    @property
    def balance(self):
        return max(self.amount - self.amount_paid, 0)

    def to_dict(self):
        return {
            "id": self.id,
            "lease_id": self.lease_id,
            "due_date": self.due_date.isoformat(),
            "amount": float(self.amount),
            "amount_paid": float(self.amount_paid),
            "balance": float(self.balance),
            "currency": self.currency,
            "status": self.status,
        }


class PaymentAllocation(db.Model):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        db.UniqueConstraint(
            "payment_id", "rent_invoice_id", name="uq_payment_allocations_payment_invoice"
        ),
        db.CheckConstraint("amount > 0", name="ck_payment_allocations_amount"),
    )

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False)
    rent_invoice_id = db.Column(
        db.Integer, db.ForeignKey("rent_invoices.id"), nullable=False
    )
    amount = db.Column(db.Numeric(12, 3), nullable=False)


class DepositLedgerEntry(db.Model):
    __tablename__ = "deposit_ledger_entries"
    __table_args__ = (
        db.CheckConstraint(
            "entry_type IN ('charge', 'payment', 'refund', 'adjustment')",
            name="ck_deposit_ledger_entry_type",
        ),
        db.CheckConstraint("amount > 0", name="ck_deposit_ledger_amount"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey("leases.id"), nullable=False, index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=True)
    entry_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 3), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "lease_id": self.lease_id,
            "payment_id": self.payment_id,
            "entry_type": self.entry_type,
            "amount": float(self.amount),
            "currency": self.currency,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }


class EmailOutbox(db.Model):
    __tablename__ = "email_outbox"
    __table_args__ = (
        db.UniqueConstraint("event_key", name="uq_email_outbox_event_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(180), nullable=False)
    recipient = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    last_error = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
