import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMyTenant } from "../../api/tenantsApi";
import {
  deleteTenantDocument,
  downloadTenantDocument,
  getMyTenantProfile,
  updateMyTenantProfile,
  uploadTenantDocument,
} from "../../api/tenantProfilesApi";
import { formatMoney } from "../../utils/money";
import "../manage.css";
import "./TenantDetailsPage.css";

const EMPTY_PROFILE = {
  full_name: "",
  phone: "",
  employment_status: "",
  employer: "",
  job_title: "",
  emergency_contact_name: "",
  emergency_contact_phone: "",
  emergency_contact_relationship: "",
  id_type: "",
  id_number: "",
  previous_landlord_name: "",
  previous_landlord_contact: "",
};

function profileToForm(profile = {}) {
  return Object.fromEntries(
    Object.keys(EMPTY_PROFILE).map((field) => [field, profile[field] ?? ""]),
  );
}

function TenantDetailsPage() {
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState(EMPTY_PROFILE);
  const [documents, setDocuments] = useState([]);
  const [residences, setResidences] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let ignore = false;
    async function loadDetails() {
      try {
        const [profileResult, tenantResult] = await Promise.all([
          getMyTenantProfile(),
          getMyTenant().catch((requestError) => {
            if (requestError.status === 404) return null;
            throw requestError;
          }),
        ]);
        if (ignore) return;
        setProfile(profileResult.profile);
        setDocuments(profileResult.documents ?? []);
        if (profileResult.profile) {
          setForm(profileToForm(profileResult.profile));
        }
        setResidences(tenantResult?.current_residences ?? []);
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    loadDetails();
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
      const result = await updateMyTenantProfile(form);
      setProfile(result.profile);
      setDocuments(result.documents ?? []);
      setForm(profileToForm(result.profile));
      setNotice("Your profile has been saved.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const result = await uploadTenantDocument(file);
      setDocuments((current) => [result.document, ...current]);
      setNotice("Document uploaded securely.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDownload(document) {
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

  async function handleDelete(documentId) {
    setError("");
    setNotice("");
    try {
      await deleteTenantDocument(documentId);
      setDocuments((current) => current.filter((item) => item.id !== documentId));
      setNotice("Document deleted.");
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  const requiredProfileFields = [
    "full_name",
    "phone",
    "employment_status",
    "emergency_contact_name",
    "emergency_contact_phone",
    "emergency_contact_relationship",
  ];
  const profileCompletion = Math.round(
    (requiredProfileFields.filter((field) => String(form[field] ?? "").trim()).length /
      requiredProfileFields.length) *
      100,
  );

  return (
    <section className="manage-page tenant-details-page">
      <header className="tenant-page-hero">
        <div className="tenant-page-hero-copy">
          <p className="tenant-page-eyebrow">TENANT WORKSPACE</p>
          <h1>Your profile</h1>
          <p>
            Keep your application details current. Each application privately
            saves a snapshot of the information you submit.
          </p>
          <div className="tenant-page-links">
            <Link to="/tenant/applications">View my applications</Link>
            <Link to="/properties">Explore properties</Link>
          </div>
        </div>
        <div className="tenant-profile-progress">
          <div>
            <span>Profile completion</span>
            <strong>{profileCompletion}%</strong>
          </div>
          <div
            className="tenant-progress-track"
            role="progressbar"
            aria-label="Profile completion"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={profileCompletion}
          >
            <span style={{ width: `${profileCompletion}%` }} />
          </div>
          <p>{profileCompletion === 100 ? "Your key details are ready for applications." : "Complete your key details to make applying easier."}</p>
        </div>
      </header>
      {loading && <p className="manage-status">Loading your profile…</p>}
      {!loading && (
        <>
          {error && <p className="manage-error tenant-profile-alert" role="alert">{error}</p>}
          {notice && <p className="tenant-profile-notice" role="status">{notice}</p>}
          <div className="tenant-details-grid">
          <form className="manage-form manage-card tenant-profile-form" onSubmit={handleSubmit}>
            <div className="tenant-form-heading">
              <div>
                <p className="tenant-page-eyebrow">APPLICATION PROFILE</p>
                <h2>Personal information</h2>
              </div>
              <span className={`tenant-profile-badge${profile ? " is-saved" : ""}`}>
                {profile ? "Profile saved" : "Not yet saved"}
              </span>
            </div>
            <label className="manage-field">
              <span>Full name</span>
              <input name="full_name" value={form.full_name} maxLength={120} required onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>Phone (international format)</span>
              <input name="phone" type="tel" value={form.phone} placeholder="+254712345678" required onChange={updateField} />
            </label>

            <h2>Employment</h2>
            <label className="manage-field">
              <span>Employment status</span>
              <input name="employment_status" value={form.employment_status} maxLength={40} required onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>Employer (optional)</span>
              <input name="employer" value={form.employer ?? ""} maxLength={120} onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>Job title (optional)</span>
              <input name="job_title" value={form.job_title ?? ""} maxLength={120} onChange={updateField} />
            </label>

            <h2>Emergency contact</h2>
            <label className="manage-field">
              <span>Name</span>
              <input name="emergency_contact_name" value={form.emergency_contact_name} maxLength={120} required onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>Phone (international format)</span>
              <input name="emergency_contact_phone" type="tel" value={form.emergency_contact_phone} placeholder="+254712345678" required onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>Relationship</span>
              <input name="emergency_contact_relationship" value={form.emergency_contact_relationship} maxLength={80} required onChange={updateField} />
            </label>

            <h2>Identity</h2>
            <label className="manage-field">
              <span>ID type (optional)</span>
              <select name="id_type" value={form.id_type ?? ""} onChange={updateField}>
                <option value="">Choose ID type</option>
                <option value="national_id">National ID</option>
                <option value="passport">Passport</option>
                <option value="drivers_license">Driver’s license</option>
                <option value="alien_id">Alien ID / residence permit</option>
                <option value="other">Other</option>
                {form.id_type && ![
                  "national_id",
                  "passport",
                  "drivers_license",
                  "alien_id",
                  "other",
                ].includes(form.id_type) && (
                  <option value={form.id_type}>{form.id_type}</option>
                )}
              </select>
            </label>
            <label className="manage-field">
              <span>ID number (encrypted at rest)</span>
              <input name="id_number" value={form.id_number ?? ""} maxLength={120} autoComplete="off" onChange={updateField} />
            </label>
            <div className="tenant-identity-upload">
              <div>
                <strong>Identity photo</strong>
                <p>Upload a clear photo or scan, or a PDF copy of the ID shown above. Up to 10 MB.</p>
              </div>
              <label className="tenant-upload-button">
                <span>{uploading ? "Uploading…" : "Upload ID photo"}</span>
                <input
                  type="file"
                  accept="application/pdf,image/jpeg,image/png,image/webp"
                  disabled={!profile || uploading}
                  onChange={handleUpload}
                />
              </label>
              {!profile && <small>Save your profile before uploading an ID photo.</small>}
            </div>

            <h2>Previous landlord (optional)</h2>
            <label className="manage-field">
              <span>Name</span>
              <input name="previous_landlord_name" value={form.previous_landlord_name ?? ""} maxLength={120} onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>Contact details</span>
              <input name="previous_landlord_contact" value={form.previous_landlord_contact ?? ""} maxLength={120} onChange={updateField} />
            </label>
            <div className="manage-actions">
              <button className="manage-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : profile ? "Save profile" : "Create profile"}
              </button>
            </div>
          </form>

          <aside className="tenant-details-sidebar">
          <section className="manage-card tenant-side-card">
            <div className="tenant-side-card-heading">
              <div>
                <p className="tenant-page-eyebrow">PRIVATE FILES</p>
                <h2>Identity documents</h2>
              </div>
              <span aria-hidden="true">↥</span>
            </div>
            <p>Private files attached to your rental application profile.</p>
            {documents.length === 0 ? (
              <p>No identity files uploaded yet.</p>
            ) : (
              <ul className="manage-list">
                {documents.map((document) => (
                  <li className="manage-card tenant-document-item" key={document.id}>
                    <span>{document.kind === "identity" ? "Identity document" : document.kind} · {Math.ceil(document.file_size / 1024)} KB</span>
                    <div className="manage-actions">
                      <button className="manage-button" type="button" onClick={() => handleDownload(document)}>
                        Download
                      </button>
                      <button className="manage-button is-danger" type="button" onClick={() => handleDelete(document.id)}>
                        Delete
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="manage-card tenant-residences tenant-side-card">
            <div>
              <p className="tenant-page-eyebrow">YOUR RENTAL</p>
              <h2>Current property</h2>
              {residences.length === 0 && (
                <p>
                  No active lease is linked to your account yet. Once an
                  application is approved and a lease is created, property
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
                    {property.address_line || property.address}, {property.city}
                    {property.region || property.state ? `, ${property.region || property.state}` : ""}
                    {property.postal_code || property.zip_code ? ` ${property.postal_code || property.zip_code}` : ""}
                    {property.country ? `, ${property.country}` : ""}
                  </p>
                  {property.description && <p>{property.description}</p>}
                  <dl>
                    <div><dt>Unit</dt><dd>{unit.unit_number}</dd></div>
                    <div><dt>Bedrooms</dt><dd>{unit.bedrooms === 0 ? "Studio" : unit.bedrooms ?? "Not specified"}</dd></div>
                    <div><dt>Bathrooms</dt><dd>{unit.bathrooms ?? "Not specified"}</dd></div>
                    <div><dt>Monthly rent</dt><dd>{formatMoney(lease.monthly_rent, lease.currency)}</dd></div>
                    <div><dt>Deposit</dt><dd>{formatMoney(lease.deposit, lease.currency)}</dd></div>
                    <div><dt>Lease dates</dt><dd>{lease.start_date} to {lease.end_date}</dd></div>
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
          </aside>
          </div>
        </>
      )}
    </section>
  );
}

export default TenantDetailsPage;
