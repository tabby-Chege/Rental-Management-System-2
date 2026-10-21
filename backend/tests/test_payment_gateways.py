from datetime import date, timedelta
from decimal import Decimal

from server.extensions import db
from server.models import Payment
from server.models_application import Application
from server.models_payment import (
    PaymentAttempt,
    PaymentAllocation,
    RentInvoice,
    RentSchedule,
)
from server.models_unit_lease import Lease
from server.payment_providers import PROVIDERS, StripeProvider
from server.payment_service import _add_month, process_rent_schedules
from tests.test_applications import apply, create_unit
from tests.test_payments import make_lease
from tests.test_tenants import client, world  # noqa: F401


def test_monthly_due_date_returns_to_configured_day_after_short_months():
    assert _add_month(date(2025, 1, 31), 31) == date(2025, 2, 28)
    assert _add_month(date(2025, 2, 28), 31) == date(2025, 3, 31)
    assert _add_month(date(2024, 1, 31), 31) == date(2024, 2, 29)
    assert _add_month(date(2024, 2, 29), 31) == date(2024, 3, 31)


def test_rent_schedule_processor_backfills_existing_active_leases(client, world):
    lease_id = make_lease(client, world)
    lease = db.session.get(Lease, lease_id)
    current_date = lease.start_date

    result = process_rent_schedules(today=current_date)

    schedule = RentSchedule.query.filter_by(lease_id=lease_id).one()
    invoice = RentInvoice.query.filter_by(lease_id=lease_id).one()
    assert result["invoices_created"] == 1
    assert schedule.due_day == lease.start_date.day
    assert invoice.due_date == lease.start_date


def enable_stripe(client):
    client.application.config.update(
        STRIPE_SECRET_KEY="sk_test_example",
        STRIPE_WEBHOOK_SECRET="whsec_example",
    )


def create_reservation(client, world):
    unit_id = create_unit(client, world["landlord"])
    application = apply(client, world["tenant"], unit_id).get_json()["application"]
    approved = client.patch(
        f"/api/applications/{application['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "The unit is available."},
    )
    assert approved.status_code == 200
    lease_end_date = (
        date.fromisoformat(application["move_in_date"]) + timedelta(days=365)
    ).isoformat()
    terms = client.patch(
        f"/api/applications/{application['id']}/lease-terms",
        headers=world["landlord"],
        json={"lease_end_date": lease_end_date},
    )
    assert terms.status_code == 200
    return terms.get_json()["application"]


def test_tenant_can_make_idempotent_partial_rent_payment(client, world, monkeypatch):
    lease_id = make_lease(client, world)
    enable_stripe(client)
    monkeypatch.setattr(
        PROVIDERS["stripe"],
        "create_checkout",
        lambda attempt: {
            "provider_reference": "cs_test_rent_1",
            "checkout_url": "https://checkout.stripe.test/session",
            "provider_data": {},
        },
    )
    monkeypatch.setattr(
        PROVIDERS["stripe"],
        "verify",
        lambda attempt, webhook=None: {
            "status": "completed",
            "provider_reference": "cs_test_rent_1",
            "amount": Decimal("500"),
            "currency": "KES",
        },
    )
    response = client.post(
        "/api/payments/checkout",
        headers={**world["tenant"], "Idempotency-Key": "rent-attempt-001"},
        json={
            "lease_id": lease_id,
            "amount": 500,
            "payment_type": "rent",
            "provider": "stripe",
        },
    )
    assert response.status_code == 201
    attempt_id = response.get_json()["attempt"]["id"]
    assert response.get_json()["attempt"]["checkout_url"]

    duplicate = client.post(
        "/api/payments/checkout",
        headers={**world["tenant"], "Idempotency-Key": "rent-attempt-001"},
        json={
            "lease_id": lease_id,
            "amount": 500,
            "payment_type": "rent",
            "provider": "stripe",
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["attempt"]["id"] == attempt_id

    status = client.get(
        f"/api/payments/attempts/{attempt_id}", headers=world["tenant"]
    )
    assert status.status_code == 200
    assert status.get_json()["attempt"]["status"] == "completed"
    with client.application.app_context():
        attempt = db.session.get(PaymentAttempt, attempt_id)
        payment = db.session.get(Payment, attempt.payment_id)
        invoice = RentInvoice.query.filter_by(lease_id=lease_id).one()
        allocation = PaymentAllocation.query.filter_by(payment_id=payment.id).one()
        assert payment.provider == "stripe"
        assert payment.provider_reference == "cs_test_rent_1"
        assert payment.currency == "KES"
        assert invoice.amount_paid == Decimal("500.000")
        assert allocation.amount == Decimal("500")
        assert Payment.query.filter_by(lease_id=lease_id).count() == 1

    repeated_status = client.get(
        f"/api/payments/attempts/{attempt_id}", headers=world["tenant"]
    )
    assert repeated_status.get_json()["attempt"]["status"] == "completed"


def test_bank_transfer_confirms_reserved_application_once(client, world):
    application = create_reservation(client, world)
    client.application.config["BANK_TRANSFER_INSTRUCTIONS"] = (
        "Transfer to the account shown on your signed lease."
    )
    checkout = client.post(
        "/api/payments/checkout",
        headers={**world["tenant"], "Idempotency-Key": "reservation-bank-001"},
        json={
            "application_id": application["id"],
            "amount": 1200,
            "payment_type": "reservation",
            "provider": "bank_transfer",
        },
    )
    assert checkout.status_code == 201
    attempt = checkout.get_json()["attempt"]
    assert attempt["instructions"]

    confirmed = client.post(
        f"/api/payments/attempts/{attempt['id']}/confirm",
        headers=world["landlord"],
        json={"provider_reference": "BANK-TRANSFER-001"},
    )
    assert confirmed.status_code == 200
    assert confirmed.get_json()["attempt"]["status"] == "completed"
    with client.application.app_context():
        current = db.session.get(Application, application["id"])
        lease = db.session.get(Lease, current.lease_id)
        assert current.status == "paid"
        assert lease is not None
        assert lease.end_date.isoformat() == application["lease_end_date"]
        assert Payment.query.filter_by(
            provider="bank_transfer", provider_reference="BANK-TRANSFER-001"
        ).count() == 1

    duplicate = client.post(
        f"/api/payments/attempts/{attempt['id']}/confirm",
        headers=world["landlord"],
        json={"provider_reference": "BANK-TRANSFER-001"},
    )
    assert duplicate.status_code == 200
    with client.application.app_context():
        assert Payment.query.filter_by(
            provider="bank_transfer", provider_reference="BANK-TRANSFER-001"
        ).count() == 1


def test_provider_webhook_is_verified_and_idempotent(client, world, monkeypatch):
    lease_id = make_lease(client, world)
    enable_stripe(client)
    monkeypatch.setattr(
        PROVIDERS["stripe"],
        "create_checkout",
        lambda attempt: {
            "provider_reference": "cs_test_webhook_1",
            "checkout_url": "https://checkout.stripe.test/session",
            "provider_data": {},
        },
    )
    monkeypatch.setattr(
        PROVIDERS["stripe"], "validate_webhook", lambda request: True
    )
    monkeypatch.setattr(
        PROVIDERS["stripe"],
        "verify",
        lambda attempt, webhook=None: {
            "status": "completed",
            "provider_reference": "cs_test_webhook_1",
            "amount": Decimal("1000"),
            "currency": "KES",
        },
    )
    checkout = client.post(
        "/api/payments/checkout",
        headers={**world["tenant"], "Idempotency-Key": "webhook-attempt-001"},
        json={"lease_id": lease_id, "amount": 1000, "provider": "stripe"},
    )
    assert checkout.status_code == 201
    webhook_body = {
        "type": "checkout.session.completed",
        "data": {"id": "cs_test_webhook_1"},
    }
    first = client.post("/api/payments/webhooks/stripe", json=webhook_body)
    second = client.post("/api/payments/webhooks/stripe", json=webhook_body)
    assert first.status_code == 200
    assert second.status_code == 200
    with client.application.app_context():
        assert Payment.query.filter_by(lease_id=lease_id).count() == 1


def test_payment_checkout_rejects_wrong_currency_and_foreign_lease(
    client, world, monkeypatch
):
    own_lease_id = make_lease(client, world)
    other_lease_id = make_lease(
        client, world, owner_key="other", tenant_key="tenant_user2"
    )
    enable_stripe(client)
    monkeypatch.setattr(
        PROVIDERS["stripe"],
        "create_checkout",
        lambda attempt: {
            "provider_reference": "unused",
            "checkout_url": "https://example.test",
            "provider_data": {},
        },
    )
    foreign = client.post(
        "/api/payments/checkout",
        headers={**world["tenant"], "Idempotency-Key": "foreign-lease-001"},
        json={"lease_id": other_lease_id, "amount": 1000, "provider": "stripe"},
    )
    assert foreign.status_code == 404

    invalid = client.post(
        "/api/payments/checkout",
        headers={**world["tenant"], "Idempotency-Key": "invalid-amount-001"},
        json={"lease_id": own_lease_id, "amount": 1.001, "provider": "stripe"},
    )
    assert invalid.status_code == 400


def test_stripe_checkout_uses_currency_minor_units(monkeypatch, client):
    observed = {}
    client.application.config["STRIPE_SECRET_KEY"] = "sk_test_example"

    def fake_request(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return {"id": "cs_test_1", "url": "https://checkout.stripe.test/1"}

    monkeypatch.setattr("server.payment_providers._request_json", fake_request)
    attempt = type(
        "Attempt",
        (),
        {
            "id": 1,
            "idempotency_key": "stripe-test",
            "currency": "KES",
            "amount": Decimal("12.34"),
            "payment_type": "rent",
            "customer_email": "tenant@example.com",
        },
    )()
    with client.application.app_context():
        result = StripeProvider().create_checkout(attempt)
    assert result["provider_reference"] == "cs_test_1"
    assert observed["form"]["line_items[0][price_data][unit_amount]"] == "1234"
    assert observed["form"]["line_items[0][price_data][currency]"] == "kes"
