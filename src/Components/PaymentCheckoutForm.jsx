import { useEffect, useState } from "react";
import {
  getPaymentAttempt,
  listPaymentProviders,
  startPaymentCheckout,
} from "../api/paymentsAPI";
import { currencyPrecision, formatMoney } from "../utils/money";

function PaymentCheckoutForm({
  leaseId,
  applicationId,
  defaultAmount,
  currency,
  paymentType = "rent",
}) {
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("");
  const [amount, setAmount] = useState(String(defaultAmount ?? ""));
  const [phoneNumber, setPhoneNumber] = useState("");
  const [attempt, setAttempt] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let ignore = false;
    listPaymentProviders()
      .then((items) => {
        if (ignore) return;
        setProviders(items);
        setProvider(items[0]?.id || "");
      })
      .catch((requestError) => {
        if (!ignore) setError(requestError.message);
      })
      .finally(() => {
        if (!ignore) setIsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!attempt || attempt.status !== "pending") return undefined;
    let ignore = false;
    const interval = window.setInterval(async () => {
      try {
        const updated = await getPaymentAttempt(attempt.id);
        if (!ignore) {
          setAttempt(updated);
          if (updated.status !== "pending") window.clearInterval(interval);
        }
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      }
    }, 15000);
    return () => {
      ignore = true;
      window.clearInterval(interval);
    };
  }, [attempt]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setIsSaving(true);
    try {
      const created = await startPaymentCheckout({
        ...(leaseId ? { lease_id: leaseId } : { application_id: applicationId }),
        amount: Number(amount),
        payment_type: paymentType,
        provider,
        ...(provider === "mpesa" ? { phone_number: phoneNumber.trim() } : {}),
      });
      setAttempt(created);
      if (created.checkout_url) window.location.assign(created.checkout_url);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return <p className="manage-status" role="status">Loading payment options…</p>;
  }

  if (error && !providers.length) {
    return <p className="manage-error" role="alert">{error}</p>;
  }

  return (
    <form className="manage-form" onSubmit={submit}>
      <label className="manage-field">
        <span>Amount ({currency})</span>
        <input
          type="number"
          min="0.01"
          step={10 ** -currencyPrecision(currency)}
          value={amount}
          required
          onChange={(event) => setAmount(event.target.value)}
        />
      </label>
      <label className="manage-field">
        <span>Payment method</span>
        <select
          value={provider}
          required
          onChange={(event) => setProvider(event.target.value)}
        >
          {providers.map((item) => (
            <option key={item.id} value={item.id}>{item.name}</option>
          ))}
        </select>
      </label>
      {provider === "mpesa" && (
        <label className="manage-field">
          <span>M-Pesa phone number</span>
          <input
            type="tel"
            value={phoneNumber}
            maxLength={20}
            required
            onChange={(event) => setPhoneNumber(event.target.value)}
            placeholder="+254712345678"
          />
        </label>
      )}
      {error && <p className="manage-error" role="alert">{error}</p>}
      <button className="manage-button" type="submit" disabled={isSaving || !provider}>
        {isSaving ? "Starting checkout…" : `Pay ${formatMoney(amount || 0, currency)}`}
      </button>
      {attempt && (
        <p className="manage-status" role="status">
          Payment status: {attempt.status}
          {attempt.status === "pending" && attempt.provider === "mpesa"
            ? ". Check your phone for the payment prompt."
            : ""}
          {attempt.status === "pending" && attempt.provider === "bank_transfer"
            ? `. ${attempt.instructions || "Follow your landlord's bank transfer instructions."}`
            : ""}
          {attempt.status === "refund_required"
            ? ". The payment arrived after the reservation expired; contact the landlord about a refund."
            : ""}
        </p>
      )}
    </form>
  );
}

export default PaymentCheckoutForm;
