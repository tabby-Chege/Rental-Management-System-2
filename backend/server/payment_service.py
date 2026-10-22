import calendar
import base64
import hashlib
import hmac
import smtplib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage

from cryptography.fernet import Fernet
from flask import current_app
from sqlalchemy import or_

from server.extensions import db
from server.models import Payment, Property, User
from server.models_application import Application
from server.models_payment import (
    DepositLedgerEntry,
    EmailOutbox,
    PaymentAllocation,
    PaymentAttempt,
    RentInvoice,
    RentSchedule,
)
from server.reservations import add_reservation_notification, as_utc
from server.models_tenant import Tenant
from server.models_unit_lease import Lease, Unit
from server.payment_providers import PROVIDERS


def utc_now():
    return datetime.now(timezone.utc)


def mfa_email_cipher():
    secret = current_app.config["JWT_SECRET_KEY"].encode("utf-8")
    key = hmac.new(
        secret,
        b"property-finder-mfa-email-outbox-v1",
        hashlib.sha256,
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_mfa_email_body(body):
    return "fernet-v1:" + mfa_email_cipher().encrypt(body.encode("utf-8")).decode("ascii")


def decrypt_mfa_email_body(body):
    prefix = "fernet-v1:"
    if not body.startswith(prefix):
        return body
    return mfa_email_cipher().decrypt(body[len(prefix):].encode("ascii")).decode("utf-8")


def queue_email(event_key, recipient, subject, body, encrypt_body=False):
    if not recipient:
        return None
    existing = EmailOutbox.query.filter_by(event_key=event_key).first()
    if existing:
        return existing
    message = EmailOutbox(
        event_key=event_key,
        recipient=recipient,
        subject=subject,
        body=encrypt_mfa_email_body(body) if encrypt_body else body,
    )
    db.session.add(message)
    return message


def add_lease_financial_records(lease):
    unit = db.session.get(Unit, lease.unit_id)
    if not unit:
        return
    currency = unit.property.currency
    schedule = RentSchedule.query.filter_by(lease_id=lease.id).first()
    if schedule:
        schedule.amount = lease.monthly_rent
        schedule.currency = currency
        schedule.active = lease.status == "active"
    elif lease.status == "active":
        schedule = RentSchedule(
            lease_id=lease.id,
            amount=lease.monthly_rent,
            currency=currency,
            due_day=lease.start_date.day,
            next_due_date=lease.start_date,
        )
        db.session.add(schedule)
    if Decimal(lease.deposit or 0) > 0:
        existing_charge = DepositLedgerEntry.query.filter_by(
            lease_id=lease.id, entry_type="charge", payment_id=None
        ).first()
        if not existing_charge:
            db.session.add(
                DepositLedgerEntry(
                    lease_id=lease.id,
                    entry_type="charge",
                    amount=lease.deposit,
                    currency=currency,
                    note="Initial lease deposit",
                )
            )


def _add_month(value, due_day=None):
    month_index = value.year * 12 + value.month
    next_year, month_zero_based = divmod(month_index, 12)
    next_month = month_zero_based + 1
    day = min(due_day or value.day, calendar.monthrange(next_year, next_month)[1])
    return date(next_year, next_month, day)


def process_rent_schedules(today=None):
    current_date = today or date.today()
    reminder_limit = current_date + timedelta(days=5)
    unscheduled_leases = (
        Lease.query.outerjoin(RentSchedule, RentSchedule.lease_id == Lease.id)
        .filter(
            Lease.status == "active",
            Lease.end_date >= current_date,
            RentSchedule.id.is_(None),
        )
        .all()
    )
    for lease in unscheduled_leases:
        add_lease_financial_records(lease)
    schedules = (
        RentSchedule.query.join(Lease, RentSchedule.lease_id == Lease.id)
        .filter(
            RentSchedule.active.is_(True),
            Lease.status == "active",
            Lease.end_date >= current_date,
            RentSchedule.next_due_date <= reminder_limit,
        )
        .order_by(RentSchedule.next_due_date, RentSchedule.id)
        .with_for_update()
        .all()
    )
    invoices_created = 0
    reminders_queued = 0
    schedules_updated = len(unscheduled_leases)

    for schedule in schedules:
        lease = db.session.get(Lease, schedule.lease_id)
        while schedule.next_due_date <= reminder_limit:
            due_date = schedule.next_due_date
            if lease and due_date > lease.end_date:
                schedule.active = False
                schedules_updated += 1
                break
            invoice = RentInvoice.query.filter_by(
                lease_id=schedule.lease_id, due_date=due_date
            ).first()
            if not invoice:
                invoice = RentInvoice(
                    lease_id=schedule.lease_id,
                    due_date=due_date,
                    amount=schedule.amount,
                    amount_paid=0,
                    currency=schedule.currency,
                    status="overdue" if due_date < current_date else "open",
                )
                db.session.add(invoice)
                db.session.flush()
                invoices_created += 1
            elif invoice.status in {"open", "partial"} and due_date < current_date:
                invoice.status = "overdue"

            tenant = (
                Tenant.query.join(Lease, Lease.tenant_id == Tenant.id)
                .filter(Lease.id == schedule.lease_id)
                .first()
            )
            user = db.session.get(User, tenant.user_id) if tenant else None
            unit = db.session.get(Unit, lease.unit_id) if lease else None
            property_record = db.session.get(Property, unit.property_id) if unit else None
            landlord = (
                db.session.get(User, property_record.owner_id)
                if property_record
                else None
            )
            days_until_due = (due_date - current_date).days
            if days_until_due <= 5 and invoice.balance > 0:
                event_type = "overdue" if days_until_due < 0 else "due"
                event_key = f"rent-invoice:{invoice.id}:{event_type}"
                subject = (
                    f"Rent overdue for lease {schedule.lease_id}"
                    if event_type == "overdue"
                    else f"Rent due on {due_date.isoformat()}"
                )
                body = (
                    f"Your rent payment of {invoice.currency} "
                    f"{invoice.balance} for lease {schedule.lease_id} is "
                    f"{'overdue' if event_type == 'overdue' else 'due'} "
                    f"on {due_date.isoformat()}."
                )
                notification = queue_email(
                    event_key, user.email if user else None, subject, body
                )
                if notification and notification.id is None:
                    reminders_queued += 1
                landlord_notification = queue_email(
                    f"rent-invoice:{invoice.id}:landlord:{event_type}",
                    landlord.email if landlord else None,
                    (
                        f"Tenant rent overdue for {property_record.name}"
                        if event_type == "overdue" and property_record
                        else f"Rent due soon for {property_record.name}"
                        if property_record
                        else f"Rent reminder for lease {schedule.lease_id}"
                    ),
                    (
                        f"Rent balance {invoice.currency} {invoice.balance} for "
                        f"{property_record.name if property_record else 'your property'}, "
                        f"unit {unit.unit_number if unit else 'unknown'} is "
                        f"{'overdue' if event_type == 'overdue' else 'due'} "
                        f"on {due_date.isoformat()}."
                    ),
                )
                if landlord_notification and landlord_notification.id is None:
                    reminders_queued += 1

            schedule.next_due_date = _add_month(due_date, schedule.due_day)
            schedules_updated += 1

    overdue_invoices = RentInvoice.query.filter(
        RentInvoice.status.in_(("open", "partial")),
        RentInvoice.due_date < current_date,
    ).all()
    for invoice in overdue_invoices:
        invoice.status = "overdue"
        lease = db.session.get(Lease, invoice.lease_id)
        tenant = (
            Tenant.query.filter_by(id=lease.tenant_id).first() if lease else None
        )
        user = db.session.get(User, tenant.user_id) if tenant else None
        notification = queue_email(
            f"rent-invoice:{invoice.id}:overdue",
            user.email if user else None,
            f"Rent overdue for lease {invoice.lease_id}",
            (
                f"Your rent payment balance of {invoice.currency} "
                f"{invoice.balance} for lease {invoice.lease_id} was due "
                f"on {invoice.due_date.isoformat()}."
            ),
        )
        if notification and notification.id is None:
            reminders_queued += 1
        unit = db.session.get(Unit, lease.unit_id) if lease else None
        property_record = db.session.get(Property, unit.property_id) if unit else None
        landlord = (
            db.session.get(User, property_record.owner_id)
            if property_record
            else None
        )
        landlord_notification = queue_email(
            f"rent-invoice:{invoice.id}:landlord:overdue",
            landlord.email if landlord else None,
            (
                f"Tenant rent overdue for {property_record.name}"
                if property_record
                else f"Rent overdue for lease {invoice.lease_id}"
            ),
            (
                f"Rent balance {invoice.currency} {invoice.balance} for "
                f"{property_record.name if property_record else 'your property'}, "
                f"unit {unit.unit_number if unit else 'unknown'} was due "
                f"on {invoice.due_date.isoformat()}."
            ),
        )
        if landlord_notification and landlord_notification.id is None:
            reminders_queued += 1

    if invoices_created or reminders_queued or schedules_updated:
        db.session.commit()
    return {
        "invoices_created": invoices_created,
        "reminders_queued": reminders_queued,
    }


def prepare_rent_invoices(lease, payment_amount):
    add_lease_financial_records(lease)
    schedule = RentSchedule.query.filter_by(lease_id=lease.id).first()
    if not schedule:
        raise ValueError("Lease does not have a recurring rent schedule")
    amount_due = sum(
        (
            Decimal(invoice.amount) - Decimal(invoice.amount_paid)
            for invoice in RentInvoice.query.filter(
                RentInvoice.lease_id == lease.id,
                RentInvoice.status.in_(("open", "partial", "overdue")),
            ).all()
        ),
        Decimal("0"),
    )
    due_date = schedule.next_due_date
    amount_to_cover = Decimal(payment_amount)
    while amount_due < amount_to_cover and due_date <= lease.end_date:
        invoice = RentInvoice.query.filter_by(
            lease_id=lease.id, due_date=due_date
        ).first()
        if not invoice:
            invoice = RentInvoice(
                lease_id=lease.id,
                due_date=due_date,
                amount=schedule.amount,
                amount_paid=0,
                currency=schedule.currency,
                status="open",
            )
            db.session.add(invoice)
            amount_due += Decimal(schedule.amount)
        due_date = _add_month(due_date, schedule.due_day)
    if amount_to_cover > amount_due:
        raise ValueError("Payment exceeds the rent remaining on this lease")


def _apply_rent_payment(payment):
    remaining = Decimal(payment.amount)
    invoices = (
        RentInvoice.query.filter(
            RentInvoice.lease_id == payment.lease_id,
            RentInvoice.status.in_(("open", "partial", "overdue")),
        )
        .order_by(RentInvoice.due_date, RentInvoice.id)
        .with_for_update()
        .all()
    )
    for invoice in invoices:
        if remaining <= 0:
            break
        balance = Decimal(invoice.amount) - Decimal(invoice.amount_paid)
        if balance <= 0:
            continue
        allocated = min(remaining, balance)
        invoice.amount_paid = Decimal(invoice.amount_paid) + allocated
        invoice.status = (
            "paid"
            if invoice.amount_paid >= invoice.amount
            else "partial"
        )
        db.session.add(
            PaymentAllocation(
                payment_id=payment.id,
                rent_invoice_id=invoice.id,
                amount=allocated,
            )
        )
        remaining -= allocated


def apply_payment_effects(payment):
    if payment.payment_type == "rent":
        _apply_rent_payment(payment)
    elif payment.payment_type == "deposit":
        existing = DepositLedgerEntry.query.filter_by(
            payment_id=payment.id, entry_type="payment"
        ).first()
        if not existing:
            db.session.add(
                DepositLedgerEntry(
                    lease_id=payment.lease_id,
                    payment_id=payment.id,
                    entry_type="payment",
                    amount=payment.amount,
                    currency=payment.currency,
                    note="Security deposit payment",
                )
            )

    lease = db.session.get(Lease, payment.lease_id)
    tenant = db.session.get(Tenant, lease.tenant_id) if lease else None
    user = db.session.get(User, tenant.user_id) if tenant else None
    queue_email(
        f"payment:{payment.id}:receipt",
        user.email if user else None,
        f"Payment receipt for lease {payment.lease_id}",
        (
            f"Payment received: {payment.currency} {payment.amount}. "
            f"Type: {payment.payment_type}. Provider: {payment.provider}. "
            f"Reference: {payment.provider_reference or payment.reference_code or 'not provided'}."
        ),
    )


def _create_payment_for_attempt(attempt, lease, provider_result):
    receipt = provider_result.get("receipt_number")
    if not isinstance(receipt, str) or not receipt.strip():
        receipt = None
    else:
        receipt = receipt.strip()
        if len(receipt) > 100:
            raise ValueError("Provider receipt reference is too long")

    payment = Payment(
        lease_id=lease.id,
        amount=attempt.amount,
        currency=attempt.currency,
        payment_method={
            "mpesa": "M-Pesa",
            "stripe": "Card or wallet",
            "paypal": "PayPal",
            "flutterwave": "Flutterwave",
            "pesapal": "Pesapal",
            "bank_transfer": "Bank Transfer",
        }.get(attempt.provider, attempt.provider),
        status="Completed",
        provider=attempt.provider,
        provider_reference=provider_result.get("provider_reference"),
        reference_code=receipt if attempt.provider == "mpesa" else None,
        payment_type=attempt.payment_type,
    )
    db.session.add(payment)
    db.session.flush()
    attempt.payment_id = payment.id

    returned_metadata = provider_result.get("provider_data")
    if isinstance(returned_metadata, dict):
        existing_metadata = (
            attempt.provider_data
            if isinstance(attempt.provider_data, dict)
            else {}
        )
        attempt.provider_data = {**existing_metadata, **returned_metadata}

    apply_payment_effects(payment)
    return payment


def finalize_payment_attempt(attempt, provider_result):
    attempt = (
        PaymentAttempt.query.filter_by(id=attempt.id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if not attempt:
        raise ValueError("Payment attempt no longer exists")
    if attempt.status == "completed":
        return attempt
    if attempt.status != "pending":
        return attempt
    if provider_result.get("status") != "completed":
        attempt.status = provider_result.get("status", "pending")
        attempt.updated_at = utc_now()
        return attempt

    paid_amount = provider_result.get("amount")
    if (
        provider_result.get("currency") != attempt.currency
        or paid_amount is None
        or Decimal(str(paid_amount)) != Decimal(attempt.amount)
    ):
        raise ValueError("Provider-confirmed amount or currency does not match the attempt")
    reference = provider_result.get("provider_reference")
    if not isinstance(reference, str) or not reference:
        raise ValueError("Provider confirmation is missing its transaction reference")
    verified_attempt_reference = (
        provider_result.get("transaction_reference")
        if attempt.provider == "flutterwave"
        else reference
    )
    if (
        attempt.provider_reference
        and verified_attempt_reference != attempt.provider_reference
    ):
        raise ValueError("Provider transaction reference does not match the attempt")

    lease = None
    if attempt.application_id is not None:
        application = (
            Application.query.filter_by(id=attempt.application_id)
            .with_for_update()
            .first()
        )
        if application and application.status in {"paid", "leased"}:
            attempt.provider_reference = attempt.provider_reference or reference
            attempt.status = "refund_required"
            attempt.updated_at = utc_now()
            attempt.completed_at = attempt.updated_at
            customer = db.session.get(User, attempt.user_id)
            queue_email(
                f"payment-attempt:{attempt.id}:already-paid",
                customer.email if customer else attempt.customer_email,
                "Duplicate reservation payment requires a refund",
                (
                    f"Provider {attempt.provider} confirmed {attempt.currency} "
                    f"{attempt.amount}, but this reservation has already been paid. "
                    "Contact the property manager to arrange a refund."
                ),
            )
            return attempt
        elif (
            not application
            or application.status not in {"approved", "offered"}
            or not application.payment_due_at
            or as_utc(application.payment_due_at) <= utc_now()
            or not application.lease_end_date
            or application.lease_end_date <= application.move_in_date
            or not application.tenant_id
        ):
            attempt.provider_reference = attempt.provider_reference or reference
            attempt.status = "refund_required"
            attempt.updated_at = utc_now()
            attempt.completed_at = attempt.updated_at
            customer = db.session.get(User, attempt.user_id)
            queue_email(
                f"payment-attempt:{attempt.id}:refund-required",
                customer.email if customer else attempt.customer_email,
                "Payment received after reservation expiry",
                (
                    f"Provider {attempt.provider} confirmed {attempt.currency} "
                    f"{attempt.amount}, but the reservation is no longer active. "
                    "Contact the property manager to arrange a refund."
                ),
            )
            return attempt
        unit = db.session.get(Unit, application.unit_id)
        if not lease and (not unit or not unit.rent_amount):
            raise ValueError("Reserved application is missing its unit rent")
        if not lease:
            lease = Lease.query.filter(
                Lease.unit_id == unit.id,
                Lease.status == "active",
                Lease.start_date <= application.lease_end_date,
                Lease.end_date >= application.move_in_date,
            ).first()
            if lease:
                attempt.provider_reference = attempt.provider_reference or reference
                attempt.status = "refund_required"
                attempt.updated_at = utc_now()
                attempt.completed_at = attempt.updated_at
                customer = db.session.get(User, attempt.user_id)
                queue_email(
                    f"payment-attempt:{attempt.id}:lease-conflict",
                    customer.email if customer else attempt.customer_email,
                    "Reservation payment requires a refund",
                    (
                        f"Provider {attempt.provider} confirmed {attempt.currency} "
                        f"{attempt.amount}, but a lease conflict prevents creating "
                        "the requested lease. Contact the property manager."
                    ),
                )
                return attempt
            lease = Lease(
                unit_id=unit.id,
                tenant_id=application.tenant_id,
                start_date=application.move_in_date,
                end_date=application.lease_end_date,
                monthly_rent=unit.rent_amount,
                deposit=0,
                status="active",
            )
            db.session.add(lease)
            db.session.flush()
            add_lease_financial_records(lease)
            application.lease_id = lease.id
            application.status = "paid"
            for queued in Application.query.filter_by(
                unit_id=unit.id, status="waitlisted"
            ).with_for_update().all():
                queued.status = "declined"
                queued.decision_reason = "The unit was leased to another applicant."
                add_reservation_notification(
                    queued,
                    "waitlist_closed",
                    "The unit was leased to another applicant.",
                    utc_now(),
                )
            add_reservation_notification(
                application,
                "payment_confirmed",
                "Your reservation payment was confirmed and your lease has been created.",
                utc_now(),
            )
        add_reservation_notification(
            application,
            "payment_confirmed",
            "Your reservation payment was confirmed and your lease has been created.",
            utc_now(),
        )
    else:
        lease = db.session.get(Lease, attempt.lease_id)
        if not lease or lease.status != "active":
            attempt.status = "failed"
            attempt.updated_at = utc_now()
            return attempt

    payment = _create_payment_for_attempt(attempt, lease, provider_result)
    attempt.provider_reference = attempt.provider_reference or reference
    attempt.status = "completed"
    attempt.completed_at = utc_now()
    attempt.updated_at = attempt.completed_at
    return attempt


def process_payment_attempt(attempt, provider):
    if attempt.status != "pending":
        return attempt
    result = provider.verify(attempt)
    return finalize_payment_attempt(attempt, result)


def process_pending_payment_attempts(limit=100):
    attempts = (
        PaymentAttempt.query.filter_by(status="pending")
        .filter(PaymentAttempt.provider != "bank_transfer")
        .order_by(PaymentAttempt.created_at, PaymentAttempt.id)
        .limit(limit)
        .with_for_update()
        .all()
    )
    counts = {
        "completed": 0,
        "failed": 0,
        "pending": 0,
        "refund_required": 0,
    }
    for attempt in attempts:
        process_payment_attempt(attempt, PROVIDERS[attempt.provider])
        counts[attempt.status] += 1
        db.session.commit()
    return counts


def process_email_outbox(limit=50):
    messages = (
        EmailOutbox.query.filter_by(status="pending")
        .order_by(EmailOutbox.created_at, EmailOutbox.id)
        .limit(limit)
        .with_for_update()
        .all()
    )
    if not messages:
        return {"sent": 0, "failed": 0}
    if current_app.config.get("MAIL_SUPPRESS_SEND"):
        for message in messages:
            message.status = "sent"
            message.sent_at = utc_now()
            if message.event_key.startswith("mfa-code:"):
                message.body = "[redacted after delivery]"
        db.session.commit()
        return {"sent": len(messages), "failed": 0}

    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("SMTP_FROM_ADDRESS")
    if not host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM_ADDRESS are required to send email")

    sent = 0
    failed = 0
    for record in messages:
        email = EmailMessage()
        email["From"] = sender
        email["To"] = record.recipient
        email["Subject"] = record.subject
        body = decrypt_mfa_email_body(record.body)
        email.set_content(body)
        try:
            with smtplib.SMTP(
                host, current_app.config["SMTP_PORT"], timeout=20
            ) as client:
                if current_app.config.get("SMTP_USE_TLS"):
                    client.starttls()
                username = current_app.config.get("SMTP_USERNAME")
                password = current_app.config.get("SMTP_PASSWORD")
                if username:
                    client.login(username, password or "")
                client.send_message(email)
        except (smtplib.SMTPException, OSError) as error:
            record.attempts += 1
            record.last_error = str(error)[:500]
            failed += 1
            continue
        record.status = "sent"
        record.attempts += 1
        record.sent_at = utc_now()
        record.last_error = None
        if record.event_key.startswith("mfa-code:"):
            record.body = "[redacted after delivery]"
        sent += 1
    db.session.commit()
    return {"sent": sent, "failed": failed}
