import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyTenant, updateMyTenant } from "../../api/tenantsApi";
import "../manage.css";

const money = (value) =>
  Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

function TenantDetailsPage() {
  const [tenant, setTenant] = useState(null);
  const [residences, setResidences] = useState([]);
  const [form, setForm] = useState({ email: "", phone: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let ignore = false;
    getMyTenant()
      .then(({ tenant: record, current_residences: currentResidences = [] }) => {
        if (ignore) return;
        setTenant(record);
        setResidences(currentResidences);
        setForm({ email: record.email ?? "", phone: record.phone ?? "" });
      })
      .catch((requestError) => {
        if (!ignore && requestError.status !== 404) {
          setError(requestError.message);
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const { tenant: updated } = await updateMyTenant(form);
      setTenant(updated);
      setForm({ email: updated.email ?? "", phone: updated.phone ?? "" });
      setNotice("Your details have been updated.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="manage-page">
      <h1>My details</h1>
      {loading && <p className="manage-status">Loading your tenant details…</p>}
      {!loading && !tenant && (
        <div className="manage-card">
          <div>
            <h2>Tenant profile not linked yet</h2>
            <p>
              Your property manager creates your tenant record when an application
              is approved. You can still browse listings and submit applications.
            </p>
          </div>
        </div>
      )}
      {!loading && tenant && (
        <>
          <form className="manage-form manage-card" onSubmit={handleSubmit}>
            <h2>{tenant.name}</h2>
            <label className="manage-field">
              <span>Email</span>
              <input
                type="email"
                value={form.email}
                maxLength={120}
                required
                onChange={(event) =>
                  setForm((current) => ({ ...current, email: event.target.value }))
                }
              />
            </label>
            <label className="manage-field">
              <span>Phone</span>
              <input
                type="tel"
                value={form.phone}
                maxLength={30}
                onChange={(event) =>
                  setForm((current) => ({ ...current, phone: event.target.value }))
                }
              />
            </label>
            {error && <p className="manage-error" role="alert">{error}</p>}
            {notice && <p role="status">{notice}</p>}
            <div className="manage-actions">
              <button className="manage-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save details"}
              </button>
            </div>
          </form>

          <section className="manage-card tenant-residences">
            <div>
              <h2>My current property</h2>
              {residences.length === 0 && (
                <p>
                  No active lease is linked to your account yet. Once your
                  application is approved and a lease is created, your property
                  details will appear here.
                </p>
              )}
            </div>
            {residences.map(({ lease, unit, property, landlord }) => (
              <article className="tenant-residence" key={lease.id}>
                <div>
                  <h3>
                    <Link to={`/properties/${property.id}`}>{property.name}</Link>
                  </h3>
                  <p>
                    {property.address}, {property.city}, {property.state}
                    {property.zip_code ? ` ${property.zip_code}` : ""}
                  </p>
                  {property.description && <p>{property.description}</p>}
                  <dl>
                    <div>
                      <dt>Unit</dt>
                      <dd>{unit.unit_number}</dd>
                    </div>
                    <div>
                      <dt>Bedrooms</dt>
                      <dd>{unit.bedrooms === 0 ? "Studio" : unit.bedrooms ?? "Not specified"}</dd>
                    </div>
                    <div>
                      <dt>Bathrooms</dt>
                      <dd>{unit.bathrooms ?? "Not specified"}</dd>
                    </div>
                    <div>
                      <dt>Monthly rent</dt>
                      <dd>{money(lease.monthly_rent)}</dd>
                    </div>
                    <div>
                      <dt>Deposit</dt>
                      <dd>{money(lease.deposit)}</dd>
                    </div>
                    <div>
                      <dt>Lease dates</dt>
                      <dd>{lease.start_date} to {lease.end_date}</dd>
                    </div>
                  </dl>
                  {landlord && (
                    <p>
                      Property manager: {landlord.name} ·{" "}
                      <a href={`mailto:${landlord.email}`}>{landlord.email}</a>
                    </p>
                  )}
                </div>
              </article>
            ))}
          </section>
        </>
      )}
      {!loading && error && !tenant && <p className="manage-error" role="alert">{error}</p>}
    </section>
  );
}

export default TenantDetailsPage;
