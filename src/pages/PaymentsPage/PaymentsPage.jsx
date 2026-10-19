import { useEffect, useState } from "react";
import { listPayments, createPayment } from "../../api/paymentsAPI";
import { listLeases } from "../../api/leasesAPI";
import { getCurrentUser } from "../../api/authAPI";
import "../manage.css";

const PER_PAGE = 10;

const INITIAL_FORM = {
  lease_id: "",
  amount: "",
  payment_method: "M-Pesa",
  status: "Pending",
  reference_code: "",
};

function formatAmount(amount) {
  return Number(amount).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString();
}

function PaymentsPage() {
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

  const [form, setForm] = useState(INITIAL_FORM);
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

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

        if (allowed) {
          const availableLeases = await listLeases();

          if (!ignore) {
            setLeases(availableLeases);
          }
        } else {
          setLeases([]);
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
    } catch (requestError) {
      setFormError(
        requestError.message || "Could not record the payment."
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="manage-page">
      <h1>Payment history</h1>

      <p className="manage-status">
        Payments are read from the records associated with your leases.
      </p>

      {canRecord && (
        <div className="manage-card">
          <h2>Record a payment</h2>

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

          {!leasesLoading && !leaseError && leases.length > 0 && (
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
                      {`Lease #${lease.id} — Tenant #${lease.tenant_id} — Unit #${lease.unit_id} — KSh ${formatAmount(lease.monthly_rent)}/month`}
                    </option>
                  ))}
                </select>
              </label>

              <label className="manage-field">
                Amount (KSh)
                <input
                  type="number"
                  name="amount"
                  value={form.amount}
                  onChange={handleChange}
                  min="0.01"
                  step="0.01"
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
              </div>
            </form>
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
                  <p>Amount: KSh {formatAmount(payment.amount)}</p>
                  <p>Method: {payment.payment_method}</p>
                  <p>
                    Reference: {payment.reference_code || "Not provided"}
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
        </>
      )}
    </section>
  );
}

export default PaymentsPage;
