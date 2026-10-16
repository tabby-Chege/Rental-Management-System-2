import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listApplications } from "../../api/applicationsApi";
import "../manage.css";

function TenantApplicationsPage() {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  return (
    <section className="manage-page">
      <h1>My applications</h1>
      <p className="manage-status">Track your requests to property managers.</p>
      {loading && <p className="manage-status">Loading applications…</p>}
      {error && <p className="manage-error" role="alert">{error}</p>}
      {!loading && !error && applications.length === 0 && (
        <div className="manage-card">
          <p>You have not applied for a unit yet.</p>
          <Link to="/properties">Browse rental properties</Link>
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
              {application.property && (
                <p>
                  {application.property.address}, {application.property.city}
                </p>
              )}
              <p>Requested move-in: {application.move_in_date}</p>
              {application.message && <p>{application.message}</p>}
            </div>
            <span className={`manage-badge is-${application.status}`}>
              {application.status}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default TenantApplicationsPage;
