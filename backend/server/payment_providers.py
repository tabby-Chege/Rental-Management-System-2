import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app

from server.money import currency_precision


PROVIDER_LABELS = {
    "mpesa": "M-Pesa",
    "stripe": "Card or wallet",
    "paypal": "PayPal",
    "flutterwave": "Flutterwave",
    "pesapal": "Pesapal",
    "bank_transfer": "Bank transfer",
}


class PaymentProviderError(Exception):
    pass


def _request_json(url, *, method="GET", headers=None, payload=None, form=None):
    request_headers = dict(headers or {})
    body = None
    if form is not None:
        body = urlencode(form).encode("utf-8")
        request_headers.setdefault(
            "Content-Type", "application/x-www-form-urlencoded"
        )
    elif payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw_response = response.read()
    except HTTPError as error:
        error.read()
        raise PaymentProviderError(
            f"Payment provider request failed with HTTP {error.code}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise PaymentProviderError("Payment provider could not be reached") from error

    if not raw_response:
        return {}
    try:
        decoded = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaymentProviderError("Payment provider returned invalid JSON") from error
    if not isinstance(decoded, dict):
        raise PaymentProviderError("Payment provider returned an invalid response")
    return decoded


def _require_config(*keys):
    missing = [key for key in keys if not current_app.config.get(key)]
    if missing:
        raise PaymentProviderError(
            "Payment provider is not configured: " + ", ".join(missing)
        )


def _amount_minor(amount, currency):
    precision = currency_precision(currency)
    if precision is None:
        raise PaymentProviderError("Unsupported currency")
    scaled = Decimal(amount) * (10 ** precision)
    if scaled != scaled.to_integral_value():
        raise PaymentProviderError("Amount cannot be represented by this provider")
    return int(scaled)


def _paypal_base():
    return (
        "https://api-m.sandbox.paypal.com"
        if current_app.config.get("PAYMENT_ENVIRONMENT") == "sandbox"
        else "https://api-m.paypal.com"
    )


def _daraja_base():
    return (
        "https://sandbox.safaricom.co.ke"
        if current_app.config.get("PAYMENT_ENVIRONMENT") == "sandbox"
        else "https://api.safaricom.co.ke"
    )


def _pesapal_base():
    return (
        "https://cybqa.pesapal.com/pesapalv3"
        if current_app.config.get("PAYMENT_ENVIRONMENT") == "sandbox"
        else "https://pay.pesapal.com/v3"
    )


def _amount_string(amount):
    return format(Decimal(amount), "f")


class BaseProvider:
    key = ""

    def create_checkout(self, attempt):
        raise NotImplementedError

    def verify(self, attempt, webhook=None):
        raise NotImplementedError

    def webhook_reference(self, payload):
        return None

    def validate_webhook(self, request):
        return True


class StripeProvider(BaseProvider):
    key = "stripe"

    def _headers(self):
        _require_config("STRIPE_SECRET_KEY")
        return {"Authorization": f"Bearer {current_app.config['STRIPE_SECRET_KEY']}"}

    def create_checkout(self, attempt):
        params = {
            "mode": "payment",
            "success_url": (
                f"{current_app.config['FRONTEND_BASE_URL']}/payments"
                f"?attempt_id={attempt.id}"
            ),
            "cancel_url": (
                f"{current_app.config['FRONTEND_BASE_URL']}/payments"
                f"?attempt_id={attempt.id}&cancelled=1"
            ),
            "customer_email": attempt.customer_email,
            "client_reference_id": attempt.idempotency_key,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": attempt.currency.lower(),
            "line_items[0][price_data][unit_amount]": str(
                _amount_minor(attempt.amount, attempt.currency)
            ),
            "line_items[0][price_data][product_data][name]": (
                f"Rental {attempt.payment_type} payment"
            ),
            "metadata[attempt_id]": str(attempt.id),
        }
        response = _request_json(
            "https://api.stripe.com/v1/checkout/sessions",
            method="POST",
            headers={
                **self._headers(),
                "Idempotency-Key": attempt.idempotency_key,
            },
            form=params,
        )
        if not response.get("id") or not response.get("url"):
            raise PaymentProviderError("Stripe did not create a checkout session")
        return {
            "provider_reference": response["id"],
            "checkout_url": response["url"],
            "provider_data": {},
        }

    def verify(self, attempt, webhook=None):
        response = _request_json(
            f"https://api.stripe.com/v1/checkout/sessions/{attempt.provider_reference}",
            headers=self._headers(),
        )
        status = (
            "completed"
            if response.get("payment_status") == "paid"
            else "failed"
            if response.get("status") == "expired"
            else "pending"
        )
        return {
            "status": status,
            "provider_reference": response.get("id"),
            "amount": Decimal(response.get("amount_total", 0))
            / (10 ** currency_precision(attempt.currency)),
            "currency": (response.get("currency") or "").upper(),
            "provider_time": response.get("created"),
        }

    def webhook_reference(self, payload):
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        return data.get("id") if isinstance(data, dict) else None

    def validate_webhook(self, request):
        secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
        signature_header = request.headers.get("Stripe-Signature", "")
        if not secret or not signature_header:
            return False
        parts = {}
        for segment in signature_header.split(","):
            key, separator, value = segment.partition("=")
            if separator:
                parts.setdefault(key, []).append(value)
        try:
            timestamp = int(parts["t"][0])
            signatures = parts["v1"]
        except (KeyError, IndexError, ValueError):
            return False
        if abs(time.time() - timestamp) > 300:
            return False
        signed_payload = str(timestamp).encode() + b"." + request.get_data()
        expected = hmac.new(
            secret.encode(), signed_payload, hashlib.sha256
        ).hexdigest()
        return any(hmac.compare_digest(expected, signature) for signature in signatures)


class PayPalProvider(BaseProvider):
    key = "paypal"

    def _access_token(self):
        _require_config("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET")
        credentials = (
            f"{current_app.config['PAYPAL_CLIENT_ID']}:"
            f"{current_app.config['PAYPAL_CLIENT_SECRET']}"
        )
        token = _request_json(
            f"{_paypal_base()}/v1/oauth2/token",
            method="POST",
            headers={
                "Authorization": "Basic "
                + base64.b64encode(credentials.encode()).decode(),
            },
            form={"grant_type": "client_credentials"},
        ).get("access_token")
        if not token:
            raise PaymentProviderError("PayPal did not issue an access token")
        return token

    def create_checkout(self, attempt):
        token = self._access_token()
        response = _request_json(
            f"{_paypal_base()}/v2/checkout/orders",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "PayPal-Request-Id": attempt.idempotency_key,
            },
            payload={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": str(attempt.id),
                        "custom_id": attempt.idempotency_key,
                        "amount": {
                            "currency_code": attempt.currency,
                            "value": _amount_string(attempt.amount),
                        },
                        "description": f"Rental {attempt.payment_type} payment",
                    }
                ],
                "application_context": {
                    "return_url": (
                        f"{current_app.config['FRONTEND_BASE_URL']}/payments"
                        f"?attempt_id={attempt.id}"
                    ),
                    "cancel_url": (
                        f"{current_app.config['FRONTEND_BASE_URL']}/payments"
                        f"?attempt_id={attempt.id}&cancelled=1"
                    ),
                },
            },
        )
        approval = next(
            (
                item.get("href")
                for item in response.get("links", [])
                if item.get("rel") in {"approve", "payer-action"}
            ),
            None,
        )
        if not response.get("id") or not approval:
            raise PaymentProviderError("PayPal did not create an approval link")
        return {
            "provider_reference": response["id"],
            "checkout_url": approval,
            "provider_data": {},
        }

    def verify(self, attempt, webhook=None):
        token = self._access_token()
        response = _request_json(
            f"{_paypal_base()}/v2/checkout/orders/{attempt.provider_reference}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.get("status") == "APPROVED":
            captured = _request_json(
                f"{_paypal_base()}/v2/checkout/orders/"
                f"{attempt.provider_reference}/capture",
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "PayPal-Request-Id": attempt.idempotency_key + "-capture",
                },
                payload={},
            )
            if captured.get("status") == "COMPLETED":
                response = captured
            else:
                response = _request_json(
                    f"{_paypal_base()}/v2/checkout/orders/"
                    f"{attempt.provider_reference}",
                    headers={"Authorization": f"Bearer {token}"},
                )
        purchase_units = response.get("purchase_units") or []
        captures = (
            (purchase_units[0].get("payments") or {}).get("captures") or []
            if purchase_units
            else []
        )
        capture = captures[0] if captures else {}
        amount = (capture.get("amount") or {}).get("value")
        currency = (capture.get("amount") or {}).get("currency_code")
        return {
            "status": (
                "completed"
                if response.get("status") == "COMPLETED"
                else "failed"
                if response.get("status") in {"VOIDED", "DENIED"}
                else "pending"
            ),
            "provider_reference": response.get("id"),
            "amount": Decimal(amount or "0"),
            "currency": currency,
            "provider_time": capture.get("create_time"),
        }

    def webhook_reference(self, payload):
        resource = payload.get("resource", {}) if isinstance(payload, dict) else {}
        supplementary = resource.get("supplementary_data", {}).get("related_ids", {})
        return supplementary.get("order_id") or resource.get("id")

    def validate_webhook(self, request):
        webhook_id = current_app.config.get("PAYPAL_WEBHOOK_ID")
        if not webhook_id:
            return False
        token = self._access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "PayPal-Transmission-Id": request.headers.get(
                "PayPal-Transmission-Id", ""
            ),
            "PayPal-Transmission-Time": request.headers.get(
                "PayPal-Transmission-Time", ""
            ),
            "PayPal-Transmission-Sig": request.headers.get(
                "PayPal-Transmission-Sig", ""
            ),
            "PayPal-Cert-Url": request.headers.get("PayPal-Cert-Url", ""),
            "PayPal-Auth-Algo": request.headers.get("PayPal-Auth-Algo", ""),
        }
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return False
        response = _request_json(
            f"{_paypal_base()}/v1/notifications/verify-webhook-signature",
            method="POST",
            headers={"Authorization": f"Bearer {token}"},
            payload={
                "auth_algo": headers["PayPal-Auth-Algo"],
                "cert_url": headers["PayPal-Cert-Url"],
                "transmission_id": headers["PayPal-Transmission-Id"],
                "transmission_sig": headers["PayPal-Transmission-Sig"],
                "transmission_time": headers["PayPal-Transmission-Time"],
                "webhook_id": webhook_id,
                "webhook_event": payload,
            },
        )
        return response.get("verification_status") == "SUCCESS"


class MpesaProvider(BaseProvider):
    key = "mpesa"

    def _access_token(self):
        _require_config("DARAJA_CONSUMER_KEY", "DARAJA_CONSUMER_SECRET")
        credentials = (
            f"{current_app.config['DARAJA_CONSUMER_KEY']}:"
            f"{current_app.config['DARAJA_CONSUMER_SECRET']}"
        )
        response = _request_json(
            f"{_daraja_base()}/oauth/v1/generate?grant_type=client_credentials",
            headers={
                "Authorization": "Basic "
                + base64.b64encode(credentials.encode()).decode()
            },
        )
        token = response.get("access_token")
        if not token:
            raise PaymentProviderError("M-Pesa did not issue an access token")
        return token

    def _password(self, timestamp):
        shortcode = current_app.config["DARAJA_SHORTCODE"]
        passkey = current_app.config["DARAJA_PASSKEY"]
        return base64.b64encode(
            f"{shortcode}{passkey}{timestamp}".encode()
        ).decode()

    def create_checkout(self, attempt):
        _require_config(
            "DARAJA_SHORTCODE", "DARAJA_PASSKEY", "DARAJA_CALLBACK_URL"
        )
        if attempt.currency != "KES" or Decimal(attempt.amount) != Decimal(
            attempt.amount
        ).to_integral_value():
            raise PaymentProviderError(
                "M-Pesa checkout requires an integer amount in KES"
            )
        phone = "".join(character for character in (attempt.phone_number or "") if character.isdigit())
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        if phone.startswith("+"):
            phone = phone[1:]
        if len(phone) != 12 or not phone.startswith("254"):
            raise PaymentProviderError("M-Pesa requires a valid Kenyan phone number")
        timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        shortcode = current_app.config["DARAJA_SHORTCODE"]
        response = _request_json(
            f"{_daraja_base()}/mpesa/stkpush/v1/processrequest",
            method="POST",
            headers={"Authorization": f"Bearer {self._access_token()}"},
            payload={
                "BusinessShortCode": shortcode,
                "Password": self._password(timestamp),
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(attempt.amount),
                "PartyA": phone,
                "PartyB": shortcode,
                "PhoneNumber": phone,
                "CallBackURL": current_app.config["DARAJA_CALLBACK_URL"],
                "AccountReference": attempt.idempotency_key[:12],
                "TransactionDesc": f"Rental {attempt.payment_type} payment",
            },
        )
        reference = response.get("CheckoutRequestID")
        if not reference:
            raise PaymentProviderError("M-Pesa did not accept the payment request")
        return {
            "provider_reference": reference,
            "checkout_url": None,
            "provider_data": {"merchant_request_id": response.get("MerchantRequestID")},
        }

    def verify(self, attempt, webhook=None):
        _require_config("DARAJA_SHORTCODE", "DARAJA_PASSKEY")

        timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        response = _request_json(
            f"{_daraja_base()}/mpesa/stkpushquery/v1/query",
            method="POST",
            headers={"Authorization": f"Bearer {self._access_token()}"},
            payload={
                "BusinessShortCode": current_app.config["DARAJA_SHORTCODE"],
                "Password": self._password(timestamp),
                "Timestamp": timestamp,
                "CheckoutRequestID": attempt.provider_reference,
            },
        )

        result_code = response.get("ResultCode")

        if result_code in (None, ""):
            return {
                "status": "pending",
                "provider_reference": attempt.provider_reference,
            }

        if str(result_code) != "0":
            return {
                "status": "failed",
                "provider_reference": attempt.provider_reference,
            }

        # A successful query does not independently provide the
        # transaction amount, receipt number, or payer phone number.
        # Do not complete the payment without callback details.
        if not isinstance(webhook, dict):
            return {
                "status": "pending",
                "provider_reference": attempt.provider_reference,
            }

        try:
            callback = webhook["Body"]["stkCallback"]
            callback_reference = callback["CheckoutRequestID"]
            callback_result_code = callback["ResultCode"]
            items = callback["CallbackMetadata"]["Item"]
        except (KeyError, TypeError):
            return {
                "status": "pending",
                "provider_reference": attempt.provider_reference,
            }

        if (
            callback_reference != attempt.provider_reference
            or str(callback_result_code) != "0"
            or not isinstance(items, list)
        ):
            return {
                "status": "pending",
                "provider_reference": attempt.provider_reference,
            }

        metadata = {
            item.get("Name"): item.get("Value")
            for item in items
            if isinstance(item, dict) and item.get("Name")
        }

        amount = metadata.get("Amount")
        receipt = metadata.get("MpesaReceiptNumber")
        callback_phone = metadata.get("PhoneNumber")

        if (
            amount is None
            or not isinstance(receipt, str)
            or not receipt.strip()
            or callback_phone is None
            or not attempt.phone_number
        ):
            return {
                "status": "pending",
                "provider_reference": attempt.provider_reference,
            }

        def normalize_phone(value):
            digits = "".join(
                character
                for character in str(value)
                if character.isdigit()
            )
            if digits.startswith("0"):
                digits = "254" + digits[1:]
            elif len(digits) == 9:
                digits = "254" + digits
            return digits

        try:
            confirmed_amount = Decimal(str(amount))
        except (ValueError, TypeError, ArithmeticError):
            return {
                "status": "pending",
                "provider_reference": attempt.provider_reference,
            }

        if (
            not confirmed_amount.is_finite()
            or confirmed_amount != Decimal(str(attempt.amount))
            or normalize_phone(callback_phone)
            != normalize_phone(attempt.phone_number)
        ):
            return {
                "status": "pending",
                "provider_reference": attempt.provider_reference,
            }

        return {
            "status": "completed",
            "provider_reference": callback_reference,
            "amount": confirmed_amount,
            "currency": "KES",
            "receipt_number": receipt.strip(),
            "provider_time": metadata.get("TransactionDate"),
            "provider_data": {
                "mpesa_receipt_number": receipt.strip(),
                "transaction_date": metadata.get("TransactionDate"),
                "phone_number": str(callback_phone),
                "merchant_request_id": callback.get("MerchantRequestID"),
            },
        }

    def webhook_reference(self, payload):
        try:
            return payload["Body"]["stkCallback"]["CheckoutRequestID"]
        except (KeyError, TypeError):
            return None


class FlutterwaveProvider(BaseProvider):
    key = "flutterwave"

    def _headers(self):
        _require_config("FLUTTERWAVE_SECRET_KEY")
        return {
            "Authorization": f"Bearer {current_app.config['FLUTTERWAVE_SECRET_KEY']}"
        }

    def create_checkout(self, attempt):
        response = _request_json(
            "https://api.flutterwave.com/v3/payments",
            method="POST",
            headers=self._headers(),
            payload={
                "tx_ref": attempt.idempotency_key,
                "amount": _amount_string(attempt.amount),
                "currency": attempt.currency,
                "redirect_url": (
                    f"{current_app.config['FRONTEND_BASE_URL']}/payments"
                    f"?attempt_id={attempt.id}"
                ),
                "customer": {"email": attempt.customer_email},
                "customizations": {
                    "title": "Rental payment",
                    "description": f"Rental {attempt.payment_type} payment",
                },
                "meta": {"attempt_id": attempt.id},
            },
        )
        data = response.get("data") or {}
        if response.get("status") != "success" or not data.get("link"):
            raise PaymentProviderError("Flutterwave did not create a checkout link")
        return {
            "provider_reference": attempt.idempotency_key,
            "checkout_url": data["link"],
            "provider_data": {},
        }

    def verify(self, attempt, webhook=None):
        transaction_id = None
        if isinstance(webhook, dict):
            data = webhook.get("data", {})
            transaction_id = data.get("id") if isinstance(data, dict) else None
        if transaction_id is None:
            query = urlencode({"tx_ref": attempt.idempotency_key})
            response = _request_json(
                f"https://api.flutterwave.com/v3/transactions?{query}",
                headers=self._headers(),
            )
            data = response.get("data")
            if isinstance(data, list) and data:
                transaction_id = data[0].get("id")
            elif isinstance(data, dict):
                transaction_id = data.get("id")
        if not transaction_id:
            return {
                "status": "pending",
                "provider_reference": attempt.idempotency_key,
                "amount": Decimal("0"),
                "currency": attempt.currency,
                "provider_time": None,
            }
        response = _request_json(
            f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
            headers=self._headers(),
        )
        data = response.get("data") or {}
        return {
            "status": (
                "completed"
                if response.get("status") == "success"
                and data.get("status") == "successful"
                else "failed"
                if data.get("status") in {"failed", "cancelled"}
                else "pending"
            ),
            "provider_reference": str(transaction_id),
            "transaction_reference": data.get("tx_ref"),
            "amount": Decimal(str(data.get("amount", "0"))),
            "currency": data.get("currency"),
            "provider_time": data.get("created_at"),
        }

    def webhook_reference(self, payload):
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        return data.get("tx_ref") if isinstance(data, dict) else None

    def validate_webhook(self, request):
        expected = current_app.config.get("FLUTTERWAVE_WEBHOOK_HASH")
        supplied = request.headers.get("verif-hash")
        return bool(
            expected
            and supplied
            and hmac.compare_digest(expected.encode(), supplied.encode())
        )


class PesapalProvider(BaseProvider):
    key = "pesapal"

    def _access_token(self):
        _require_config(
            "PESAPAL_CONSUMER_KEY", "PESAPAL_CONSUMER_SECRET", "PESAPAL_IPN_ID"
        )
        response = _request_json(
            f"{_pesapal_base()}/api/Auth/RequestToken",
            method="POST",
            payload={
                "consumer_key": current_app.config["PESAPAL_CONSUMER_KEY"],
                "consumer_secret": current_app.config["PESAPAL_CONSUMER_SECRET"],
            },
        )
        token = response.get("token")
        if not token:
            raise PaymentProviderError("Pesapal did not issue an access token")
        return token

    def create_checkout(self, attempt):
        _require_config("PESAPAL_CALLBACK_URL")
        token = self._access_token()
        response = _request_json(
            f"{_pesapal_base()}/api/Transactions/SubmitOrderRequest",
            method="POST",
            headers={"Authorization": f"Bearer {token}"},
            payload={
                "id": str(attempt.id),
                "currency": attempt.currency,
                "amount": float(attempt.amount),
                "description": f"Rental {attempt.payment_type} payment",
                "callback_url": current_app.config["PESAPAL_CALLBACK_URL"],
                "notification_id": current_app.config["PESAPAL_IPN_ID"],
                "billing_address": {"email_address": attempt.customer_email},
            },
        )
        reference = response.get("order_tracking_id")
        checkout_url = response.get("redirect_url")
        if not reference or not checkout_url:
            raise PaymentProviderError("Pesapal did not create a checkout session")
        return {
            "provider_reference": str(reference),
            "checkout_url": checkout_url,
            "provider_data": {
                "merchant_reference": response.get("merchant_reference")
            },
        }

    def verify(self, attempt, webhook=None):
        token = self._access_token()
        query = urlencode({"orderTrackingId": attempt.provider_reference})
        response = _request_json(
            f"{_pesapal_base()}/api/Transactions/GetTransactionStatus?{query}",
            headers={"Authorization": f"Bearer {token}"},
        )
        status = str(response.get("payment_status_description", "")).upper()
        return {
            "status": (
                "completed"
                if status == "COMPLETED"
                else "failed"
                if status in {"FAILED", "INVALID", "REVERSED"}
                else "pending"
            ),
            "provider_reference": str(response.get("order_tracking_id") or attempt.provider_reference),
            "amount": Decimal(str(response.get("amount", "0"))),
            "currency": response.get("currency"),
            "provider_time": response.get("created_date"),
        }

    def webhook_reference(self, payload):
        if isinstance(payload, dict):
            return payload.get("OrderTrackingId") or payload.get("orderTrackingId")
        return None


PROVIDERS = {
    provider.key: provider()
    for provider in (
        MpesaProvider,
        StripeProvider,
        PayPalProvider,
        FlutterwaveProvider,
        PesapalProvider,
    )
}


def provider_is_configured(provider):
    required = {
        "mpesa": (
            "DARAJA_CONSUMER_KEY",
            "DARAJA_CONSUMER_SECRET",
            "DARAJA_SHORTCODE",
            "DARAJA_PASSKEY",
            "DARAJA_CALLBACK_URL",
        ),
        "stripe": ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"),
        "paypal": (
            "PAYPAL_CLIENT_ID",
            "PAYPAL_CLIENT_SECRET",
            "PAYPAL_WEBHOOK_ID",
        ),
        "flutterwave": ("FLUTTERWAVE_SECRET_KEY", "FLUTTERWAVE_WEBHOOK_HASH"),
        "pesapal": (
            "PESAPAL_CONSUMER_KEY",
            "PESAPAL_CONSUMER_SECRET",
            "PESAPAL_CALLBACK_URL",
            "PESAPAL_IPN_ID",
        ),
    }
    return provider in required and all(
        current_app.config.get(key) for key in required[provider]
    )


def configured_providers():
    return [
        {"id": key, "name": PROVIDER_LABELS[key]}
        for key in (*PROVIDERS, "bank_transfer")
        if key == "bank_transfer" or provider_is_configured(key)
    ]
