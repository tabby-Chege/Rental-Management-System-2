import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listApplications } from "../api/applicationsApi";
import { listConversations } from "../api/conversationsApi";
import { listMaintenanceRequests, getPortfolioReport } from "../api/landlordToolsApi";
import { listRentInvoices } from "../api/paymentsAPI";

function LandlordDashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");
  const [currentMonth] = useState(() => {
    const date = new Date();
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
  });

  useEffect(() => {
    let ignore = false;
    Promise.all([
      getPortfolioReport(),
      listApplications(),
      listMaintenanceRequests(),
      listConversations(),
      listRentInvoices(),
    ])
      .then(([report, applications, maintenance, conversations, invoices]) => {
        if (!ignore) {
          setDashboard({ report, applications, maintenance, conversations, invoices });
        }
      })
      .catch((requestError) => {
        if (!ignore) setError(requestError.message);
      });
    return () => {
      ignore = true;
    };
  }, []);

  if (error) {
    return (
      <section className="workspace-dashboard">
        <p className="manage-error" role="alert">{error}</p>
      </section>
    );
  }
  if (!dashboard) {
    return <section className="workspace-dashboard"><p>Loading your portfolio…</p></section>;
  }

  const properties = dashboard.report.properties ?? [];
  const totals = properties.reduce((summary, property) => ({
    occupied: summary.occupied + (property.occupied_units ?? 0),
    vacant: summary.vacant + (property.vacant_units ?? 0),
  }), { occupied: 0, vacant: 0 });
  const pending = dashboard.applications.filter((item) => item.status === "pending");
  const openMaintenance = dashboard.maintenance.filter(
    (item) => !["resolved", "closed"].includes(item.status),
  );
  const unread = dashboard.conversations.reduce(
    (count, conversation) => count + (conversation.unread_count ?? 0),
    0,
  );
  const rentDue = dashboard.invoices
    .filter((invoice) => invoice.due_date.startsWith(currentMonth) && invoice.balance > 0)
    .reduce((totalsByCurrency, invoice) => {
      totalsByCurrency.set(
        invoice.currency,
        (totalsByCurrency.get(invoice.currency) ?? 0) + invoice.balance,
      );
      return totalsByCurrency;
    }, new Map());
  const arrearsByCurrency = properties.reduce((totalsByCurrency, property) => {
    totalsByCurrency.set(
      property.currency,
      (totalsByCurrency.get(property.currency) ?? 0) + Number(property.rent_arrears ?? 0),
    );
    return totalsByCurrency;
  }, new Map());
  const formatCurrencyTotals = (totalsByCurrency) => (
    [...totalsByCurrency.entries()]
      .map(([currency, amount]) => `${currency} ${amount.toLocaleString()}`)
      .join(" · ") || "KES 0"
  );
  const attention = [
    ...pending.slice(0, 3).map((application) => ({
      key: `application-${application.id}`,
      title: `Application from ${application.applicant?.name ?? "a tenant"}`,
      detail: `${application.property?.name ?? "Property"} · Unit ${application.unit?.unit_number ?? application.unit_id}`,
      to: "/manage/applications",
    })),
    ...openMaintenance.slice(0, 3).map((request) => ({
      key: `maintenance-${request.id}`,
      title: request.title,
      detail: `${request.property_name ?? "Property"} · Unit ${request.unit_number ?? ""} · ${request.status.replaceAll("_", " ")}`,
      to: "/maintenance",
    })),
  ].slice(0, 6);

  return (
    <section className="workspace-dashboard">
      <header className="workspace-dashboard-heading">
        <div>
          <p className="workspace-eyebrow">LANDLORD WORKSPACE</p>
          <h1>Portfolio overview</h1>
          <p>Here’s what needs your attention across the properties you manage.</p>
        </div>
        <Link className="manage-button" to="/manage/properties">Manage properties</Link>
      </header>
      <div className="workspace-stat-grid">
        <Link className="workspace-stat-card" to="/units">
          <span>Occupied / vacant units</span><strong>{totals.occupied} / {totals.vacant}</strong>
          <small>Across {properties.length} properties</small>
        </Link>
        <Link className="workspace-stat-card" to="/reports">
          <span>Rent due this month</span><strong>{formatCurrencyTotals(rentDue)}</strong>
          <small>{formatCurrencyTotals(arrearsByCurrency)} in past-due arrears</small>
        </Link>
        <Link className="workspace-stat-card" to="/maintenance">
          <span>Open maintenance</span><strong>{openMaintenance.length}</strong>
          <small>Requests awaiting resolution</small>
        </Link>
        <Link className="workspace-stat-card" to="/manage/applications">
          <span>Pending applications</span><strong>{pending.length}</strong>
          <small>Ready for your review</small>
        </Link>
        <Link className="workspace-stat-card" to="/messages">
          <span>Unread messages</span><strong>{unread}</strong>
          <small>Across your property conversations</small>
        </Link>
      </div>
      <div className="workspace-dashboard-lower">
        <section className="workspace-panel">
          <div className="workspace-panel-heading">
            <div><p className="workspace-eyebrow">PRIORITY QUEUE</p><h2>Needs attention</h2></div>
          </div>
          {attention.length ? (
            <ul className="workspace-attention-list">
              {attention.map((item) => (
                <li key={item.key}>
                  <div><strong>{item.title}</strong><small>{item.detail}</small></div>
                  <Link to={item.to}>Review</Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="workspace-empty">You’re all caught up. New applications and maintenance requests will show here.</p>
          )}
        </section>
        <section className="workspace-panel workspace-shortcuts">
          <p className="workspace-eyebrow">QUICK ACCESS</p>
          <h2>Manage your rentals</h2>
          <Link to="/manage/applications">Review applications <span>→</span></Link>
          <Link to="/payments">View payment history <span>→</span></Link>
          <Link to="/reports">Open portfolio reports <span>→</span></Link>
          <Link to="/messages">Go to messages <span>→</span></Link>
        </section>
      </div>
    </section>
  );
}

export default LandlordDashboardPage;
