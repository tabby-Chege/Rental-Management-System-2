import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  decideApplication,
  listApplications,
} from "../../api/applicationsApi";
import "../manage.css";

function leaseUrl(application, prefill = {}) {
  const values = {
    tenant_id: prefill.tenant_id ?? application.tenant_id,
    unit_id: prefill.unit_id ?? application.unit_id,
    start_date: prefill.start_date ?? application.move_in_date,
    monthly_rent: prefill.monthly_rent ?? application.unit?.rent_amount,
  };
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return `/leases?${params.toString()}`;
}

function ManageApplicationsPage() {
  const navigate = useNavigate();
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);

  useEffect(() => {
    let ignore = false;
    listApplications()
      .then((items) => {
        if (!ignore) setApplications(items);
      })
      .catch((requestError) => {
        if (!ignore) setError(requestError.message);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  async function decide(application, status) {
    setError("");
    setSavingId(application.id);
    try {
      const result = await decideApplication(application.id, status);
      setApplications((current) =>
        current.map((item) =>
          item.id === application.id ? result.application : item
        )
      );
      if (status === "approved" && result.lease_prefill) {
        navigate(leaseUrl(result.application, result.lease_prefill));
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingId(null);
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
              <p>Requested move-in: {application.move_in_date}</p>
              {application.message && <p>{application.message}</p>}
            </div>
            <div>
              <span className={`manage-badge is-${application.status}`}>
                {application.status}
              </span>
              {application.status === "pending" ? (
                <div className="manage-actions">
                  <button
                    className="manage-button"
                    type="button"
                    disabled={savingId === application.id}
                    onClick={() => decide(application, "approved")}
                  >
                    {savingId === application.id ? "Saving…" : "Approve"}
                  </button>
                  <button
                    className="manage-button is-danger"
                    type="button"
                    disabled={savingId === application.id}
                    onClick={() => decide(application, "declined")}
                  >
                    Decline
                  </button>
                </div>
              ) : application.status === "approved" ? (
                <p>
                  <Link to={leaseUrl(application)}>Create lease</Link>
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
