import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listApplications } from "../api/applicationsApi";
import { listConversations } from "../api/conversationsApi";
import { listMaintenanceRequests } from "../api/landlordToolsApi";
import { listRentInvoices } from "../api/paymentsAPI";
import { getMyTenant } from "../api/tenantsApi";
import { listMyLeases } from "../api/leasesAPI";
import { formatMoney } from "../utils/money";

function TenantDashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    Promise.all([
      getMyTenant().catch((requestError) => {
        if (requestError.status === 404) return null;
        throw requestError;
      }),
      listMyLeases(),
      listApplications(),
      listMaintenanceRequests(),
      listConversations(),
      listRentInvoices(),
    ])
      .then(([tenant, leases, applications, maintenance, conversations, invoices]) => {
        if (!ignore) setData({ tenant, leases, applications, maintenance, conversations, invoices });
      })
      .catch((requestError) => {
        if (!ignore) setError(requestError.message);
      });
    return () => {
      ignore = true;
    };
  }, []);

  if (error) {
    return <section className="workspace-dashboard"><p className="manage-error" role="alert">{error}</p></section>;
  }
  if (!data) {
    return <section className="workspace-dashboard"><p>Loading your home…</p></section>;
  }

  const residence = data.tenant?.current_residences?.[0];
  const activeLease = data.leases.find((lease) => lease.status === "active");
  const openMaintenance = data.maintenance.filter(
    (item) => !["resolved", "closed"].includes(item.status),
  );
  const recentMessages = [...data.conversations]
    .sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at))
    .slice(0, 3);
  const applications = data.applications.slice(0, 4);
  const nextInvoice = data.invoices
    .filter((invoice) => invoice.balance > 0)
    .sort((left, right) => left.due_date.localeCompare(right.due_date))[0];

  return (
    <section className="workspace-dashboard tenant-home">
      <header className="workspace-dashboard-heading">
        <div>
          <p className="workspace-eyebrow">TENANT WORKSPACE</p>
          <h1>Welcome home</h1>
          <p>Your rental, applications and important updates in one place.</p>
        </div>
        <Link className="manage-button" to="/properties">Find a place</Link>
      </header>
      <section className="workspace-home-card">
        <div>
          <p className="workspace-eyebrow">MY HOME</p>
          {residence ? (
            <>
              <h2>{residence.property?.name ?? "Your rental"}</h2>
              <p>
                Unit {residence.unit?.unit_number ?? "—"}
                {residence.property?.city ? ` · ${residence.property.city}` : ""}
              </p>
              <dl>
                <div><dt>Monthly rent</dt><dd>{formatMoney(residence.lease?.monthly_rent, residence.lease?.currency)}</dd></div>
                <div><dt>Lease dates</dt><dd>{residence.lease?.start_date} – {residence.lease?.end_date}</dd></div>
                <div><dt>Next payment due</dt><dd>{nextInvoice?.due_date ?? "No upcoming invoice"}</dd></div>
              </dl>
            </>
          ) : (
            <>
              <h2>No active home yet</h2>
              <p>Browse available rentals or track the status of your applications.</p>
            </>
          )}
        </div>
        <div className="workspace-home-actions">
          {residence && <Link className="manage-button" to="/payments">Pay rent</Link>}
          <Link to={residence ? "/lease-documents" : "/tenant/applications"}>
            {residence ? "View lease documents" : "Track my applications"}
          </Link>
        </div>
      </section>
      <div className="workspace-dashboard-lower">
        <section className="workspace-panel">
          <div className="workspace-panel-heading">
            <div><p className="workspace-eyebrow">RENTAL UPDATES</p><h2>My applications</h2></div>
            <Link to="/tenant/applications">View all</Link>
          </div>
          {applications.length ? (
            <ul className="workspace-attention-list">
              {applications.map((application) => (
                <li key={application.id}>
                  <div>
                    <strong>{application.property?.name ?? "Property"} · Unit {application.unit?.unit_number ?? application.unit_id}</strong>
                    <small>Submitted {new Date(application.created_at).toLocaleDateString()}</small>
                  </div>
                  <span className={`manage-badge is-${application.status}`}>{application.status}</span>
                </li>
              ))}
            </ul>
          ) : <p className="workspace-empty">No applications yet. Browse rentals when you’re ready.</p>}
        </section>
        <section className="workspace-panel">
          <div className="workspace-panel-heading">
            <div><p className="workspace-eyebrow">YOUR RENTAL</p><h2>Maintenance</h2></div>
            <Link to="/maintenance">Open maintenance</Link>
          </div>
          {openMaintenance.length ? (
            <ul className="workspace-attention-list">
              {openMaintenance.slice(0, 3).map((request) => (
                <li key={request.id}>
                  <div><strong>{request.title}</strong><small>{request.property_name} · {request.status.replaceAll("_", " ")}</small></div>
                </li>
              ))}
            </ul>
          ) : <p className="workspace-empty">No open maintenance requests.</p>}
        </section>
        <section className="workspace-panel">
          <div className="workspace-panel-heading">
            <div><p className="workspace-eyebrow">CONVERSATIONS</p><h2>Recent messages</h2></div>
            <Link to="/messages">Open inbox</Link>
          </div>
          {recentMessages.length ? (
            <ul className="workspace-attention-list">
              {recentMessages.map((conversation) => (
                <li key={conversation.id}>
                  <div>
                    <strong>{conversation.other_party?.name ?? "Property manager"}</strong>
                    <small>{conversation.latest_message?.body ?? "Open conversation"}</small>
                  </div>
                  <Link to={`/messages?conversation=${conversation.id}`}>Open</Link>
                </li>
              ))}
            </ul>
          ) : <p className="workspace-empty">Your landlord conversations will appear here.</p>}
          {activeLease && <p className="workspace-lease-note">Lease #{activeLease.id} is active.</p>}
        </section>
      </div>
    </section>
  );
}

export default TenantDashboardPage;
