import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listApplications } from "../../api/applicationsApi";
import PaymentCheckoutForm from "../../Components/PaymentCheckoutForm";
import ReservationCountdown from "../../Components/ReservationCountdown";
import {
  listNotifications,
  markNotificationRead,
} from "../../api/notificationsApi";
import "../manage.css";

function formatPropertyDate(value, timeZone) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timeZone || "UTC",
  }).format(new Date(value));
}

function TenantApplicationsPage() {
  const [applications, setApplications] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    async function load(initial = false) {
      try {
        const [items, notices] = await Promise.all([
          listApplications(),
          listNotifications(),
        ]);
        if (!ignore) {
          setApplications(items);
          setNotifications(notices);
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

  async function markRead(notification) {
    setError("");
    try {
      const updated = await markNotificationRead(notification.id);
      setNotifications((current) =>
        current.map((item) => item.id === updated.id ? updated : item)
      );
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <section className="manage-page">
      <h1>My applications</h1>
      <p className="manage-status">Track your requests to property managers.</p>
      {loading && <p className="manage-status">Loading applications…</p>}
      {!loading && notifications.length > 0 && (
        <section aria-label="Reservation notifications">
          <h2>Reservation updates</h2>
          <ul className="manage-list">
            {notifications.map((notification) => {
              const application = applications.find(
                (item) => item.id === notification.application_id,
              );
              return (
                <li className="manage-card" key={notification.id}>
                  <div>
                    <p>{notification.message}</p>
                    <small>
                      {formatPropertyDate(
                        notification.created_at,
                        application?.property?.time_zone,
                      )}
                    </small>
                  </div>
                  {!notification.read_at && (
                    <button
                      className="manage-button is-secondary"
                      type="button"
                      onClick={() => markRead(notification)}
                    >
                      Mark as read
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
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
                  {application.property.address_line || application.property.address}, {application.property.city}
                </p>
              )}
              <p>Requested move-in: {application.move_in_date}</p>
              {application.message && <p>{application.message}</p>}
              {application.payment_due_at && (
                <>
                  <p>
                    Payment deadline:{" "}
                    {formatPropertyDate(
                      application.payment_due_at,
                      application.property?.time_zone,
                    )}
                  </p>
                  {["approved", "offered"].includes(application.status) && (
                    <ReservationCountdown deadline={application.payment_due_at} />
                  )}
                </>
              )}
              {["approved", "offered"].includes(application.status) && (
                application.lease_end_date ? (
                  <details>
                    <summary>Pay reservation</summary>
                    <p>Lease term ends: {application.lease_end_date}</p>
                    <PaymentCheckoutForm
                      applicationId={application.id}
                      defaultAmount={application.unit?.rent_amount}
                      currency={application.unit?.currency || "KES"}
                      paymentType="reservation"
                    />
                  </details>
                ) : (
                  <p>The landlord must set the lease end date before payment checkout is available.</p>
                )
              )}
              {application.status === "waitlisted" && (
                <p>You are on the waitlist. We will notify you if the unit becomes available.</p>
              )}
              {application.status === "expired" && (
                <p>The reservation expired before payment was confirmed.</p>
              )}
              {application.status === "paid" && (
                <p>Payment is confirmed; your lease will begin on the requested move-in date.</p>
              )}
              {application.status === "leased" && <p>Your lease has started.</p>}
              {application.decision_reason && (
                <p>Decision reason: {application.decision_reason}</p>
              )}
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
