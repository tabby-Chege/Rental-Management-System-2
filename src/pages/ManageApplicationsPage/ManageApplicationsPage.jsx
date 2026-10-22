import { useEffect, useState } from "react";
import {
  confirmReservationPayment,
  decideApplication,
  listApplications,
  setApplicationLeaseTerms,
} from "../../api/applicationsApi";
import { downloadTenantDocument } from "../../api/tenantProfilesApi";
import ReservationCountdown from "../../Components/ReservationCountdown";
import { currencyPrecision } from "../../utils/money";
import "../manage.css";

function formatPropertyDate(value, timeZone) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timeZone || "UTC",
  }).format(new Date(value));
}

function dayAfter(value) {
  return new Date(`${value}T00:00:00Z`)
    .toISOString()
    .slice(0, 10);
}

function ReservationPaymentForm({ application, isSaving, onConfirm }) {
  const [leaseEndDate, setLeaseEndDate] = useState(
    application.lease_end_date || "",
  );
  const [amount, setAmount] = useState(
    application.unit?.rent_amount == null
      ? ""
      : String(application.unit.rent_amount),
  );
  const [paymentMethod, setPaymentMethod] = useState("Bank Transfer");
  const [referenceCode, setReferenceCode] = useState("");
  const currency = application.unit?.currency || "KES";

  return (
    <form
      className="manage-form"
      onSubmit={(event) => {
        event.preventDefault();
        onConfirm(application.id, {
          lease_end_date: leaseEndDate,
          amount: Number(amount),
          payment_method: paymentMethod,
          reference_code: referenceCode.trim() || null,
        });
      }}
    >
      <p>Use this after payment has been received and verified.</p>
      <label className="manage-field">
        <span>Lease end date</span>
        <input
          type="date"
          min={dayAfter(application.move_in_date)}
          value={leaseEndDate}
          required
          onChange={(event) => setLeaseEndDate(event.target.value)}
        />
      </label>
      <label className="manage-field">
        <span>Confirmed amount ({currency})</span>
        <input
          type="number"
          min="0"
          step={10 ** -currencyPrecision(currency)}
          value={amount}
          required
          onChange={(event) => setAmount(event.target.value)}
        />
      </label>
      <label className="manage-field">
        <span>Payment method</span>
        <select
          value={paymentMethod}
          onChange={(event) => setPaymentMethod(event.target.value)}
        >
          <option value="Bank Transfer">Bank transfer</option>
          <option value="M-Pesa">M-Pesa</option>
          <option value="Cash">Cash</option>
        </select>
      </label>
      <label className="manage-field">
        <span>Payment reference (optional)</span>
        <input
          value={referenceCode}
          maxLength={100}
          onChange={(event) => setReferenceCode(event.target.value)}
        />
      </label>
      <button className="manage-button" type="submit" disabled={isSaving}>
        {isSaving ? "Confirming…" : "Confirm payment and create lease"}
      </button>
    </form>
  );
}

function LeaseTermsForm({ application, isSaving, onSave }) {
  const [leaseEndDate, setLeaseEndDate] = useState(
    application.lease_end_date || "",
  );
  return (
    <form
      className="manage-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(application.id, leaseEndDate);
      }}
    >
      <label className="manage-field">
        <span>Lease end date (required before tenant checkout)</span>
        <input
          type="date"
          min={dayAfter(application.move_in_date)}
          value={leaseEndDate}
          required
          onChange={(event) => setLeaseEndDate(event.target.value)}
        />
      </label>
      <button className="manage-button is-secondary" type="submit" disabled={isSaving}>
        {isSaving ? "Saving…" : "Save lease terms"}
      </button>
    </form>
  );
}

function ManageApplicationsPage() {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [decision, setDecision] = useState(null);
  const [decisionReason, setDecisionReason] = useState("");

  useEffect(() => {
    let ignore = false;
    async function load(initial = false) {
      try {
        const items = await listApplications();
        if (!ignore) {
          setApplications(items);
          setError("");
        }
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      } finally {
        if (initial && !ignore) setLoading(false);
      }
    }
    load(true);
    const interval = window.setInterval(() => load(), 15000);
    return () => {
      ignore = true;
      window.clearInterval(interval);
    };
  }, []);

  async function decide(application, status) {
    setError("");
    setSavingId(application.id);
    try {
      await decideApplication(
        application.id,
        status,
        decisionReason.trim(),
      );
      setApplications(await listApplications());
      setDecision(null);
      setDecisionReason("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingId(null);
    }
  }

  async function confirmPayment(applicationId, values) {
    setError("");
    setSavingId(applicationId);
    try {
      await confirmReservationPayment(applicationId, values);
      setApplications(await listApplications());
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingId(null);
    }
  }

  async function saveLeaseTerms(applicationId, leaseEndDate) {
    setError("");
    setSavingId(applicationId);
    try {
      await setApplicationLeaseTerms(applicationId, leaseEndDate);
      setApplications(await listApplications());
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingId(null);
    }
  }

  async function downloadDocument(document) {
    setError("");
    try {
      const blob = await downloadTenantDocument(document.id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = `tenant-document-${document.id}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <section className="manage-page">
      <h1>Rental applications</h1>
      <p className="manage-status">
        Review requests for units in the properties you manage.
      </p>
      {error && <p className="manage-error" role="alert">{error}</p>}
      {loading && <p className="manage-status">Loading applications…</p>}
      {!loading && !error && applications.length === 0 && (
        <div className="manage-card">
          <p>No tenant applications have been received.</p>
        </div>
      )}
      <ul className="manage-list">
        {applications.map((application) => (
          <li className="manage-card" key={application.id}>
            <div>
              <strong>
                {application.property?.name ?? "Property"} — Unit{" "}
                {application.unit?.unit_number ?? `#${application.unit_id}`}
              </strong>
              <p>
                {application.applicant?.name ?? "Tenant"} (
                {application.applicant?.email ?? "email unavailable"})
              </p>
              <details>
                <summary>Applicant profile snapshot</summary>
                <dl>
                  <div><dt>Phone</dt><dd>{application.applicant_profile?.phone || "Not provided"}</dd></div>
                  <div><dt>Employment</dt><dd>{application.applicant_profile?.employment_status || "Not provided"}</dd></div>
                  <div><dt>Employer</dt><dd>{application.applicant_profile?.employer || "Not provided"}</dd></div>
                  <div><dt>Job title</dt><dd>{application.applicant_profile?.job_title || "Not provided"}</dd></div>
                  <div><dt>Emergency contact</dt><dd>{application.applicant_profile?.emergency_contact_name || "Not provided"} · {application.applicant_profile?.emergency_contact_phone || ""}</dd></div>
                  <div><dt>ID details</dt><dd>{application.applicant_profile?.id_type || "Not provided"} {application.applicant_profile?.id_number || ""}</dd></div>
                  <div><dt>Previous landlord</dt><dd>{application.applicant_profile?.previous_landlord_name || "Not provided"} · {application.applicant_profile?.previous_landlord_contact || ""}</dd></div>
                </dl>
                <ul>
                  {(application.applicant_profile?.documents ?? []).map((document) => (
                    <li key={document.id}>
                      {document.kind} · {Math.ceil(document.file_size / 1024)} KB{" "}
                      <button type="button" onClick={() => downloadDocument(document)}>
                        Download document
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
              <p>Requested move-in: {application.move_in_date}</p>
              {application.message && <p>{application.message}</p>}
              {application.decision_reason && <p>Decision reason: {application.decision_reason}</p>}
              {application.payment_due_at && (
                <>
                  <p>
                    Payment deadline:{" "}
                    {formatPropertyDate(
                      application.payment_due_at,
                      application.property?.time_zone,
                    )}
                  </p>
                  <ReservationCountdown deadline={application.payment_due_at} />
                </>
              )}
            </div>
            <div>
              <span className={`manage-badge is-${application.status}`}>
                {application.status}
              </span>
              {application.status === "pending" || application.status === "waitlisted" ? (
                <>
                  <div className="manage-actions">
                    {application.status === "pending" && (
                      <button
                        className="manage-button"
                        type="button"
                        disabled={savingId === application.id}
                        onClick={() => {
                          setDecision({ id: application.id, status: "approved" });
                          setDecisionReason("");
                        }}
                      >
                        Approve
                      </button>
                    )}
                    <button
                      className="manage-button is-danger"
                      type="button"
                      disabled={savingId === application.id}
                      onClick={() => {
                        setDecision({ id: application.id, status: "declined" });
                        setDecisionReason("");
                      }}
                    >
                      Decline
                    </button>
                  </div>
                  {decision?.id === application.id && (
                    <form
                      className="manage-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        decide(application, decision.status);
                      }}
                    >
                      <label className="manage-field">
                        <span>Reason for {decision.status}</span>
                        <textarea
                          value={decisionReason}
                          maxLength={1000}
                          required
                          onChange={(event) => setDecisionReason(event.target.value)}
                        />
                      </label>
                      <div className="manage-actions">
                        <button className="manage-button" type="submit" disabled={savingId === application.id}>
                          {savingId === application.id ? "Saving…" : `Confirm ${decision.status}`}
                        </button>
                        <button className="manage-button is-danger" type="button" onClick={() => setDecision(null)}>
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}
                </>
              ) : ["approved", "offered"].includes(application.status) ? (
                <>
                  <LeaseTermsForm
                    key={`lease-terms-${application.id}-${application.lease_end_date || ""}`}
                    application={application}
                    isSaving={savingId === application.id}
                    onSave={saveLeaseTerms}
                  />
                  <ReservationPaymentForm
                    key={application.id}
                    application={application}
                    isSaving={savingId === application.id}
                    onConfirm={confirmPayment}
                  />
                </>
              ) : application.status === "paid" || application.status === "leased" ? (
                <p>
                  Payment confirmed. Lease #{application.lease_id} was created.
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default ManageApplicationsPage;
