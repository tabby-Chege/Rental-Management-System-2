import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  confirmBankTransfer,
  createDepositLedgerEntry,
  createPayment,
  getDepositLedger,
  getPaymentAttempt,
  listPaymentAttempts,
  listPayments,
  listRentInvoices,
} from "../../api/paymentsAPI";
import { listLeases, listMyLeases } from "../../api/leasesAPI";
import { getCurrentUser } from "../../api/authAPI";
import { CURRENCY_CODES, currencyPrecision, formatMoney } from "../../utils/money";
import PaymentCheckoutForm from "../../Components/PaymentCheckoutForm";
import "../manage.css";

const PER_PAGE = 10;

const INITIAL_FORM = {
  lease_id: "",
  amount: "",
  payment_method: "M-Pesa",
  status: "Pending",
  reference_code: "",
};

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString();
}

function PaymentsPage() {
  const [searchParams] = useSearchParams();
  const attemptId = searchParams.get("attempt_id");
  const [payments, setPayments] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  const [canRecord, setCanRecord] = useState(false);
  const [leases, setLeases] = useState([]);
  const [leasesLoading, setLeasesLoading] = useState(true);
  const [leaseError, setLeaseError] = useState("");
  const [invoices, setInvoices] = useState([]);
  const [depositLedger, setDepositLedger] = useState({ entries: [], balances: [] });
  const [pendingTransfers, setPendingTransfers] = useState([]);
  const [transferReferences, setTransferReferences] = useState({});
  const [depositForm, setDepositForm] = useState({
    lease_id: "",
    entry_type: "refund",
    amount: "",
    note: "",
  });
  const [returnedAttempt, setReturnedAttempt] = useState(null);
  const [paymentFormOpen, setPaymentFormOpen] = useState(false);
  const [depositFormOpen, setDepositFormOpen] = useState(false);
  const [depositSaving, setDepositSaving] = useState(false);

  const [form, setForm] = useState(INITIAL_FORM);
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const selectedLease = leases.find((lease) => String(lease.id) === form.lease_id);
  const currency = selectedLease?.currency || CURRENCY_CODES[0];
  const selectedDepositLease = leases.find(
    (lease) => String(lease.id) === depositForm.lease_id,
  );
  const depositPrecision = currencyPrecision(
    selectedDepositLease?.currency || CURRENCY_CODES[0],
  );

  // Determine the user's role and load leases for authorized users.
  useEffect(() => {
    let ignore = false;

    async function loadFormData() {
      setLeasesLoading(true);
      setLeaseError("");

      try {
        const result = await getCurrentUser();
        const role = result.user?.role;
        const allowed = role === "landlord" || role === "admin";

        if (ignore) return;

        setCanRecord(allowed);
        const [availableLeases, availableInvoices, availableDeposits] =
          await Promise.all([
            allowed ? listLeases() : role === "tenant" ? listMyLeases() : [],
            listRentInvoices(),
            getDepositLedger(),
          ]);
        if (!ignore) {
          setLeases(availableLeases);
          setInvoices(availableInvoices);
          setDepositLedger(availableDeposits);
        }
        if (allowed) {
          const attempts = await listPaymentAttempts({ status: "pending" });
          if (!ignore) {
            setPendingTransfers(
              attempts.filter((attempt) => attempt.provider === "bank_transfer"),
            );
          }
        }
      } catch (requestError) {
        if (!ignore) {
          setCanRecord(false);
          setLeases([]);
          setLeaseError(
            requestError.message || "Could not load available leases."
          );
        }
      } finally {
        if (!ignore) setLeasesLoading(false);
      }
    }

    loadFormData();

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!attemptId) return undefined;
    let ignore = false;
    let interval;
    const loadAttempt = async () => {
      try {
        const attempt = await getPaymentAttempt(attemptId);
        if (!ignore) {
          setReturnedAttempt(attempt);
          if (attempt.status !== "pending" && interval) {
            window.clearInterval(interval);
          }
        }
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      }
    };
    loadAttempt();
    interval = window.setInterval(loadAttempt, 15000);
    return () => {
      ignore = true;
      window.clearInterval(interval);
    };
  }, [attemptId]);

  // Load the existing payment history.
  useEffect(() => {
    let ignore = false;

    async function loadPayments() {
      setIsLoading(true);
      setError("");

      try {
        const result = await listPayments({
          page,
          perPage: PER_PAGE,
        });

        if (!ignore) {
          setPayments(result.payments || []);
          setPagination(result.pagination || null);
        }
      } catch (requestError) {
        if (!ignore) {
          setPayments([]);
          setPagination(null);
          setError(
            requestError.message || "Could not load payment history."
          );
        }
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }

    loadPayments();

    return () => {
      ignore = true;
    };
  }, [page, retryCount]);

  function handleChange(event) {
    const { name, value } = event.target;

    setForm((current) => ({
      ...current,
      [name]: value,
    }));

    setFormError("");
    setSuccessMessage("");
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setFormError("");
    setSuccessMessage("");

    const amount = Number(form.amount);
    const leaseId = Number(form.lease_id);

    if (!form.lease_id || !Number.isInteger(leaseId) || leaseId <= 0) {
      setFormError("Please select a lease.");
      return;
    }

    if (!form.amount.trim() || !Number.isFinite(amount) || amount <= 0) {
      setFormError("Enter a valid amount greater than zero.");
      return;
    }
    const precision = currencyPrecision(currency);
    if (amount !== Number(amount.toFixed(precision))) {
      setFormError(`Amount may have at most ${precision} decimal places for ${currency}.`);
      return;
    }

    const referenceCode = form.reference_code.trim();

    if (referenceCode.length > 100) {
      setFormError("The reference code cannot exceed 100 characters.");
      return;
    }

    setIsSaving(true);

    try {
      await createPayment({
        lease_id: leaseId,
        amount,
        payment_method: form.payment_method,
        status: form.status,
        reference_code: referenceCode || null,
      });

      setForm(INITIAL_FORM);
      setPage(1);
      setRetryCount((count) => count + 1);
      setSuccessMessage("Payment recorded successfully.");
      setPaymentFormOpen(false);
    } catch (requestError) {
      setFormError(
        requestError.message || "Could not record the payment."
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmTransfer(attempt) {
    setFormError("");
    const reference = (transferReferences[attempt.id] || "").trim();
    if (!reference) {
      setFormError("Enter the bank transfer reference before confirming.");
      return;
    }
    try {
      await confirmBankTransfer(attempt.id, reference);
      setPendingTransfers((current) =>
        current.filter((item) => item.id !== attempt.id),
      );
      setRetryCount((count) => count + 1);
      setSuccessMessage("Bank transfer confirmed.");
    } catch (requestError) {
      setFormError(requestError.message || "Could not confirm the transfer.");
    }
  }

  async function recordDepositEntry(event) {
    event.preventDefault();
    setFormError("");
    if (!depositForm.lease_id || Number(depositForm.amount) <= 0) {
      setFormError("Select a lease and enter a positive deposit amount.");
      return;
    }
    setDepositSaving(true);
    try {
      await createDepositLedgerEntry({
        ...depositForm,
        lease_id: Number(depositForm.lease_id),
        amount: Number(depositForm.amount),
      });
      setDepositFormOpen(false);
      setDepositForm((current) => ({ ...current, amount: "", note: "" }));
      setSuccessMessage("Deposit ledger entry saved.");
      try {
        setDepositLedger(await getDepositLedger());
      } catch (requestError) {
        setFormError(`Deposit entry saved, but the ledger could not be refreshed: ${requestError.message}`);
        return;
      }
      setSuccessMessage("Deposit ledger updated.");
    } catch (requestError) {
      setFormError(requestError.message || "Could not update the deposit ledger.");
    } finally {
      setDepositSaving(false);
    }
  }

  return (
    <section className="manage-page">
      <h1>Payment history</h1>

      <p className="manage-status">
        Payments are read from the records associated with your leases.
      </p>
      {formError && <p className="manage-error" role="alert">{formError}</p>}
      {successMessage && <p className="manage-status" role="status">{successMessage}</p>}

      {returnedAttempt && (
        <div className="manage-card" role="status">
          <strong>Checkout status: {returnedAttempt.status}</strong>
          {returnedAttempt.status === "pending" && (
            <p>Payment confirmation is still pending. This status refreshes automatically.</p>
          )}
          {returnedAttempt.status === "refund_required" && (
            <p>The reservation expired before this payment was confirmed. Contact the landlord about a refund.</p>
          )}
        </div>
      )}

      {!canRecord && leases.length > 0 && (
        <section aria-label="Pay rent">
          <h2>Pay rent or deposit</h2>
          <ul className="manage-list">
            {leases.filter((lease) => lease.status === "active").map((lease) => {
              const balance = depositLedger.balances?.find(
                (item) => item.lease_id === lease.id,
              );
              return (
                <li className="manage-card" key={lease.id}>
                  <div>
                    <strong>Lease #{lease.id}</strong>
                    <p>Rent: {formatMoney(lease.monthly_rent, lease.currency)} per month</p>
                    <PaymentCheckoutForm
                      leaseId={lease.id}
                      defaultAmount={lease.monthly_rent}
                      currency={lease.currency}
                    />
                    {(balance?.outstanding > 0 || balance?.held > 0) && (
                      <>
                        <p>
                          Deposit balance: {formatMoney(balance.outstanding, balance.currency)}
                          {" · "}Held: {formatMoney(balance.held, balance.currency)}
                        </p>
                        {balance.outstanding > 0 && (
                          <PaymentCheckoutForm
                            leaseId={lease.id}
                            defaultAmount={balance.outstanding}
                            currency={balance.currency}
                            paymentType="deposit"
                          />
                        )}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {invoices.length > 0 && (
        <section aria-label="Rent invoices">
          <h2>Rent due dates</h2>
          <ul className="manage-list">
            {invoices.map((invoice) => (
              <li className="manage-card" key={invoice.id}>
                <strong>Lease #{invoice.lease_id} · Due {invoice.due_date}</strong>
                <p>
                  {formatMoney(invoice.amount_paid, invoice.currency)} paid of{" "}
                  {formatMoney(invoice.amount, invoice.currency)} · Balance{" "}
                  {formatMoney(invoice.balance, invoice.currency)}
                </p>
                <span className={`manage-badge is-${invoice.status}`}>{invoice.status}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {canRecord && pendingTransfers.length > 0 && (
        <section className="manage-card" aria-label="Bank transfers awaiting confirmation">
          <h2>Bank transfers awaiting confirmation</h2>
          {pendingTransfers.map((attempt) => (
            <div className="manage-form" key={attempt.id}>
              <p>
                Attempt #{attempt.id}: {formatMoney(attempt.amount, attempt.currency)}
                {" · "}Lease/application #{attempt.lease_id || attempt.application_id}
              </p>
              <label className="manage-field">
                Provider reference
                <input
                  value={transferReferences[attempt.id] || ""}
                  maxLength={160}
                  onChange={(event) => setTransferReferences((current) => ({
                    ...current,
                    [attempt.id]: event.target.value,
                  }))}
                />
              </label>
              <button
                className="manage-button"
                type="button"
                onClick={() => confirmTransfer(attempt)}
              >
                Confirm transfer
              </button>
            </div>
          ))}
        </section>
      )}
      {canRecord && leases.length > 0 && (
        <section className="manage-card payment-entry-card" aria-label="Manage deposit ledger">
          <h2>Record deposit charge or refund</h2>
          <button type="button" className="manage-button is-secondary" onClick={() => {
            setFormError("");
            setSuccessMessage("");
            setDepositFormOpen(true);
          }}>
            Add ledger entry
          </button>
          {depositFormOpen && (
          <div className="manage-dialog-backdrop">
          <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="deposit-entry-dialog-title">
          <div className="manage-dialog-heading">
            <div>
              <h2 id="deposit-entry-dialog-title">Record deposit charge or refund</h2>
              <p>Choose a lease and enter the deposit ledger adjustment.</p>
            </div>
            <button type="button" className="manage-dialog-close" aria-label="Close deposit form" disabled={depositSaving} onClick={() => setDepositFormOpen(false)}>×</button>
          </div>
          <form className="manage-form" onSubmit={recordDepositEntry}>
            <label className="manage-field">
              Lease
              <select
                value={depositForm.lease_id}
                required
                onChange={(event) => setDepositForm((current) => ({
                  ...current,
                  lease_id: event.target.value,
                }))}
              >
                <option value="">Select a lease</option>
                {leases.map((lease) => (
                  <option key={lease.id} value={lease.id}>
                    Lease #{lease.id} · {formatMoney(lease.monthly_rent, lease.currency)}/month
                  </option>
                ))}
              </select>
            </label>
            <label className="manage-field">
              Entry
              <select
                value={depositForm.entry_type}
                onChange={(event) => setDepositForm((current) => ({
                  ...current,
                  entry_type: event.target.value,
                }))}
              >
                <option value="charge">Additional deposit charge</option>
                <option value="refund">Deposit refund</option>
              </select>
            </label>
            <label className="manage-field">
              Amount ({selectedDepositLease?.currency || CURRENCY_CODES[0]})
              <input
                type="number"
                min={10 ** -depositPrecision}
                step={10 ** -depositPrecision}
                value={depositForm.amount}
                required
                onChange={(event) => setDepositForm((current) => ({
                  ...current,
                  amount: event.target.value,
                }))}
              />
            </label>
            <label className="manage-field">
              Note
              <input
                value={depositForm.note}
                maxLength={500}
                onChange={(event) => setDepositForm((current) => ({
                  ...current,
                  note: event.target.value,
                }))}
              />
            </label>
            <div className="manage-actions">
              <button className="manage-button" type="submit" disabled={depositSaving}>
                {depositSaving ? "Saving…" : "Save ledger entry"}
              </button>
              <button type="button" className="manage-button is-secondary" disabled={depositSaving} onClick={() => setDepositFormOpen(false)}>
                Cancel
              </button>
            </div>
          </form>
          </section>
          </div>
          )}
        </section>
      )}

      {canRecord && (
        <div className="manage-card">
          <h2>Record a payment</h2>
          {!leasesLoading && !leaseError && leases.length > 0 && (
            <button type="button" className="manage-button" onClick={() => {
              setFormError("");
              setSuccessMessage("");
              setPaymentFormOpen(true);
            }}>
              Record payment
            </button>
          )}

          {leasesLoading && (
            <p className="manage-status" role="status">
              Loading available leases…
            </p>
          )}

          {leaseError && (
            <p className="manage-error" role="alert">
              {leaseError}
            </p>
          )}

          {!leasesLoading && !leaseError && leases.length === 0 && (
            <p className="manage-status">
              No leases are available. Create a lease before recording
              a payment.
            </p>
          )}

          {!leasesLoading && !leaseError && leases.length > 0 && paymentFormOpen && (
            <div className="manage-dialog-backdrop">
            <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="record-payment-dialog-title">
            <div className="manage-dialog-heading">
              <div>
                <h2 id="record-payment-dialog-title">Record a payment</h2>
                <p>Record a received payment against the correct lease.</p>
              </div>
              <button type="button" className="manage-dialog-close" aria-label="Close payment form" disabled={isSaving} onClick={() => setPaymentFormOpen(false)}>×</button>
            </div>
            <form className="manage-form" onSubmit={handleSubmit}>
              <label className="manage-field">
                Lease
                <select
                  name="lease_id"
                  value={form.lease_id}
                  onChange={handleChange}
                  required
                >
                  <option value="">Select a lease</option>

                  {leases.map((lease) => (
                    <option key={lease.id} value={lease.id}>
                      {`Lease #${lease.id} — Tenant #${lease.tenant_id} — Unit #${lease.unit_id} — ${formatMoney(lease.monthly_rent, lease.currency)}/month`}
                    </option>
                  ))}
                </select>
              </label>

              <label className="manage-field">
                Amount ({currency})
                <input
                  type="number"
                  name="amount"
                  value={form.amount}
                  onChange={handleChange}
                  min="0.01"
                  step={10 ** -currencyPrecision(currency)}
                  required
                />
              </label>

              <label className="manage-field">
                Payment method
                <select
                  name="payment_method"
                  value={form.payment_method}
                  onChange={handleChange}
                  required
                >
                  <option value="M-Pesa">M-Pesa</option>
                  <option value="Bank Transfer">Bank Transfer</option>
                  <option value="Cash">Cash</option>
                </select>
              </label>

              <label className="manage-field">
                Payment status
                <select
                  name="status"
                  value={form.status}
                  onChange={handleChange}
                  required
                >
                  <option value="Pending">Pending</option>
                  <option value="Completed">Completed</option>
                  <option value="Failed">Failed</option>
                </select>
              </label>

              <label className="manage-field">
                Reference code (optional)
                <input
                  type="text"
                  name="reference_code"
                  value={form.reference_code}
                  onChange={handleChange}
                  maxLength={100}
                  placeholder="e.g. M-Pesa transaction code"
                />
              </label>

              {formError && (
                <p className="manage-error" role="alert">
                  {formError}
                </p>
              )}

              {successMessage && (
                <p className="manage-status" role="status">
                  {successMessage}
                </p>
              )}

              <div className="manage-actions">
                <button
                  type="submit"
                  className="manage-button"
                  disabled={isSaving}
                >
                  {isSaving ? "Saving payment…" : "Record payment"}
                </button>
                <button type="button" className="manage-button is-secondary" disabled={isSaving} onClick={() => setPaymentFormOpen(false)}>
                  Cancel
                </button>
              </div>
            </form>
            </section>
            </div>
          )}

          {leasesLoading && formError && (
            <p className="manage-error" role="alert">
              {formError}
            </p>
          )}
        </div>
      )}

      {isLoading && (
        <p className="manage-status" role="status">
          Loading payment history…
        </p>
      )}

      {error && (
        <div className="manage-card">
          <p className="manage-error" role="alert">
            {error}
          </p>

          <button
            type="button"
            className="manage-button"
            onClick={() => setRetryCount((count) => count + 1)}
          >
            Try again
          </button>
        </div>
      )}

      {!isLoading && !error && payments.length === 0 && (
        <div className="manage-card">
          <p>No payment history is available yet.</p>
        </div>
      )}

      {!isLoading && !error && payments.length > 0 && (
        <>
          <ul className="manage-list">
            {payments.map((payment) => (
              <li className="manage-card" key={payment.id}>
                <div>
                  <strong>
                    {payment.property_name} — Unit {payment.unit_number}
                  </strong>

                  <p>Tenant: {payment.tenant_name}</p>
                  <p>Payment date: {formatDate(payment.payment_date)}</p>
                  <p>Amount: {formatMoney(payment.amount, payment.currency)}</p>
                  <p>Method: {payment.payment_method}</p>
                  <p>Type: {payment.payment_type}</p>
                  <p>Provider: {payment.provider}</p>
                  <p>
                    Reference: {payment.provider_reference || payment.reference_code || "Not provided"}
                  </p>

                  <span
                    className={`manage-badge is-${payment.status.toLowerCase()}`}
                  >
                    {payment.status}
                  </span>
                </div>
              </li>
            ))}
          </ul>

          {pagination?.pages > 1 && (
            <nav
              className="pagination-controls"
              aria-label="Payment history pages"
            >
              <button
                type="button"
                onClick={() => setPage((current) => current - 1)}
                disabled={!pagination.has_prev}
              >
                Previous
              </button>

              <span>
                Page {pagination.page} of {pagination.pages}
              </span>

              <button
                type="button"
                onClick={() => setPage((current) => current + 1)}
                disabled={!pagination.has_next}
              >
                Next
              </button>
            </nav>
          )}

          {depositLedger.entries?.length > 0 && (
            <section aria-label="Deposit ledger">
              <h2>Deposit ledger</h2>
              <ul className="manage-list">
                {(depositLedger.balances || []).map((balance) => (
                  <li className="manage-card" key={balance.lease_id}>
                    <strong>Lease #{balance.lease_id}</strong>
                    <p>
                      Charged {formatMoney(balance.charged, balance.currency)} ·
                      Received {formatMoney(balance.paid, balance.currency)} ·
                      Held {formatMoney(balance.held, balance.currency)} ·
                      Outstanding {formatMoney(balance.outstanding, balance.currency)}
                    </p>
                  </li>
                ))}
              </ul>
              <ul className="manage-list">
                {depositLedger.entries.map((entry) => (
                  <li className="manage-card" key={entry.id}>
                    <strong>Lease #{entry.lease_id} · {entry.entry_type}</strong>
                    <p>{formatMoney(entry.amount, entry.currency)}{entry.note ? ` · ${entry.note}` : ""}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </section>
  );
}

export default PaymentsPage;
