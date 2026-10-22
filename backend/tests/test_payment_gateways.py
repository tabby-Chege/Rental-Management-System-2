from types import SimpleNamespace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from server.extensions import db
from server.models import Payment
from server.models_application import Application
from server.models_payment import (
    EmailOutbox,
    PaymentAttempt,
    PaymentAllocation,
    RentInvoice,
    RentSchedule,
)
from server.models_unit_lease import Lease
from server.payment_providers import PROVIDERS, StripeProvider, MpesaProvider
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


def test_rent_reminders_are_sent_to_tenant_and_landlord_once(client, world):
    lease_id = make_lease(client, world)
    lease = db.session.get(Lease, lease_id)

    process_rent_schedules(today=lease.start_date)
    messages = EmailOutbox.query.order_by(EmailOutbox.id).all()

    assert {message.recipient for message in messages} == {
        "tom@x.com",
        "lana@x.com",
    }
    count = len(messages)
    process_rent_schedules(today=lease.start_date)
    assert EmailOutbox.query.count() == count


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


def test_payment_after_reservation_expiry_is_refunded_and_promotes_waitlist(
    client, world, monkeypatch
):
    unit_id = create_unit(client, world["landlord"])
    first = apply(client, world["tenant"], unit_id).get_json()["application"]
    second = apply(client, world["tenant2"], unit_id).get_json()["application"]
    approval = client.patch(
        f"/api/applications/{first['id']}",
        headers=world["landlord"],
        json={"status": "approved", "reason": "The application is complete."},
    )
    assert approval.status_code == 200
    lease_end_date = (
        date.fromisoformat(first["move_in_date"]) + timedelta(days=365)
    ).isoformat()
    assert client.patch(
        f"/api/applications/{first['id']}/lease-terms",
        headers=world["landlord"],
        json={"lease_end_date": lease_end_date},
    ).status_code == 200

    enable_stripe(client)
    monkeypatch.setattr(
        PROVIDERS["stripe"],
        "create_checkout",
        lambda attempt: {
            "provider_reference": "cs_test_expired_reservation",
            "checkout_url": "https://checkout.stripe.test/expired",
            "provider_data": {},
        },
    )
    monkeypatch.setattr(
        PROVIDERS["stripe"],
        "verify",
        lambda attempt, webhook=None: {
            "status": "completed",
            "provider_reference": "cs_test_expired_reservation",
            "amount": Decimal("1200"),
            "currency": "KES",
        },
    )
    checkout = client.post(
        "/api/payments/checkout",
        headers={**world["tenant"], "Idempotency-Key": "expired-reservation-001"},
        json={
            "application_id": first["id"],
            "amount": 1200,
            "payment_type": "reservation",
            "provider": "stripe",
        },
    )
    assert checkout.status_code == 201
    attempt_id = checkout.get_json()["attempt"]["id"]

    fixed_now = datetime.now(timezone.utc) + timedelta(seconds=10)
    with client.application.app_context():
        application = db.session.get(Application, first["id"])
        application.payment_due_at = fixed_now - timedelta(seconds=1)
        db.session.commit()
    monkeypatch.setattr("server.reservations.utc_now", lambda: fixed_now)

    checked = client.get(
        f"/api/payments/attempts/{attempt_id}",
        headers=world["tenant"],
    )
    assert checked.status_code == 200
    assert checked.get_json()["attempt"]["status"] == "refund_required"
    with client.application.app_context():
        expired = db.session.get(Application, first["id"])
        promoted = db.session.get(Application, second["id"])
        assert expired.status == "expired"
        assert expired.lease_id is None
        assert promoted.status == "offered"
        assert promoted.payment_due_at.replace(tzinfo=timezone.utc) == (
            fixed_now + timedelta(hours=1)
        )
        assert Lease.query.filter_by(unit_id=unit_id).count() == 0
        assert Payment.query.filter_by(payment_type="reservation").count() == 0


def test_concurrent_reservation_payment_attempts_cannot_create_two_leases(
    client, world
):
    application = create_reservation(client, world)
    checkout_attempts = []
    for key in ("duplicate-reservation-001", "duplicate-reservation-002"):
        checkout = client.post(
            "/api/payments/checkout",
            headers={**world["tenant"], "Idempotency-Key": key},
            json={
                "application_id": application["id"],
                "amount": 1200,
                "payment_type": "reservation",
                "provider": "bank_transfer",
            },
        )
        assert checkout.status_code == 201
        checkout_attempts.append(checkout.get_json()["attempt"]["id"])

    first = client.post(
        f"/api/payments/attempts/{checkout_attempts[0]}/confirm",
        headers=world["landlord"],
        json={"provider_reference": "BANK-TRANSFER-CONCURRENT-001"},
    )
    second = client.post(
        f"/api/payments/attempts/{checkout_attempts[1]}/confirm",
        headers=world["landlord"],
        json={"provider_reference": "BANK-TRANSFER-CONCURRENT-002"},
    )

    assert first.status_code == 200
    assert first.get_json()["attempt"]["status"] == "completed"
    assert second.status_code == 200
    assert second.get_json()["attempt"]["status"] == "refund_required"
    with client.application.app_context():
        current = db.session.get(Application, application["id"])
        assert current.status == "paid"
        assert Lease.query.filter_by(unit_id=current.unit_id).count() == 1
        assert Payment.query.filter_by(payment_type="reservation").count() == 1


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


def _setup_mpesa_verification_test(client, monkeypatch, result_code="0"):
    client.application.config.update(
        DARAJA_SHORTCODE="174379",
        DARAJA_PASSKEY="test-passkey",
    )

    provider = MpesaProvider()
    attempt = SimpleNamespace(
        provider_reference="ws_CO_TEST123",
        amount=Decimal("500"),
        phone_number="0712345678",
    )

    monkeypatch.setattr(
        provider,
        "_access_token",
        lambda: "test-access-token",
    )
    monkeypatch.setattr(
        "server.payment_providers._request_json",
        lambda *args, **kwargs: {"ResultCode": result_code},
    )

    callback = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "merchant-test",
                "CheckoutRequestID": "ws_CO_TEST123",
                "ResultCode": 0,
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 500},
                        {"Name": "MpesaReceiptNumber", "Value": "TESTRECEIPT1"},
                        {"Name": "TransactionDate", "Value": 20261021150000},
                        {"Name": "PhoneNumber", "Value": 254712345678},
                    ]
                },
            }
        }
    }

    return provider, attempt, callback


def test_mpesa_verification_accepts_matching_successful_callback(
    client, monkeypatch
):
    provider, attempt, callback = _setup_mpesa_verification_test(
        client, monkeypatch
    )

    with client.application.app_context():
        result = provider.verify(attempt, callback)

    assert result["status"] == "completed"
    assert result["amount"] == Decimal("500")
    assert result["currency"] == "KES"
    assert result["provider_reference"] == "ws_CO_TEST123"
    assert result["receipt_number"] == "TESTRECEIPT1"


def test_mpesa_verification_rejects_incorrect_amount(
    client, monkeypatch
):
    provider, attempt, callback = _setup_mpesa_verification_test(
        client, monkeypatch
    )
    callback["Body"]["stkCallback"]["CallbackMetadata"]["Item"][0]["Value"] = 700

    with client.application.app_context():
        result = provider.verify(attempt, callback)

    assert result["status"] == "pending"


def test_mpesa_verification_rejects_mismatched_phone(
    client, monkeypatch
):
    provider, attempt, callback = _setup_mpesa_verification_test(
        client, monkeypatch
    )
    callback["Body"]["stkCallback"]["CallbackMetadata"]["Item"][3]["Value"] = (
        254799999999
    )

    with client.application.app_context():
        result = provider.verify(attempt, callback)

    assert result["status"] == "pending"


def test_mpesa_verification_stays_pending_without_callback_metadata(
    client, monkeypatch
):
    provider, attempt, _ = _setup_mpesa_verification_test(
        client, monkeypatch
    )

    with client.application.app_context():
        result = provider.verify(attempt, {})

    assert result["status"] == "pending"


def test_mpesa_verification_marks_unsuccessful_query_as_failed(
    client, monkeypatch
):
    provider, attempt, callback = _setup_mpesa_verification_test(
        client, monkeypatch, result_code="1032"
    )

    with client.application.app_context():
        result = provider.verify(attempt, callback)

    assert result["status"] == "failed"

def test_mpesa_receipt_and_provider_metadata_are_persisted(client, world):
    from server.payment_service import _create_payment_for_attempt

    lease_id = make_lease(client, world)
    lease = db.session.get(Lease, lease_id)

    attempt = PaymentAttempt(
        user_id=world["ids"]["tenant_user"],
        lease_id=lease_id,
        idempotency_key="mpesa-receipt-persistence-test",
        provider="mpesa",
        provider_reference="ws_CO_PERSIST123",
        amount=Decimal("500"),
        currency="KES",
        payment_type="rent",
        status="pending",
        customer_email="tenant@example.com",
        phone_number="0712345678",
        provider_data={"merchant_request_id": "merchant-persist-test"},
    )
    db.session.add(attempt)
    db.session.flush()

    result = {
        "provider_reference": "ws_CO_PERSIST123",
        "receipt_number": "TESTRECEIPT99",
        "provider_data": {
            "receipt_number": "TESTRECEIPT99",
            "transaction_date": "20261021150000",
            "phone_number": "254712345678",
        },
    }

    with client.application.app_context():
        payment = _create_payment_for_attempt(attempt, lease, result)
        db.session.flush()

        assert payment.reference_code == "TESTRECEIPT99"
        assert payment.provider_reference == "ws_CO_PERSIST123"
        assert attempt.payment_id == payment.id
        assert attempt.provider_data["merchant_request_id"] == "merchant-persist-test"
        assert attempt.provider_data["receipt_number"] == "TESTRECEIPT99"
        assert attempt.provider_data["transaction_date"] == "20261021150000"
        assert attempt.provider_data["phone_number"] == "254712345678"
