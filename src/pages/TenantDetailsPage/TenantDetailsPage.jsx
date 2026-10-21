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
          setForm({ ...EMPTY_PROFILE, ...profileResult.profile });
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
      setForm({ ...EMPTY_PROFILE, ...result.profile });
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

  return (
    <section className="manage-page">
      <h1>My profile</h1>
      <p className="manage-status">
        Keep your application information up to date. A submitted application
        keeps a private snapshot of the details you provided at that time.
      </p>
      {loading && <p className="manage-status">Loading your profile…</p>}
      {!loading && (
        <>
          <form className="manage-form manage-card" onSubmit={handleSubmit}>
            <h2>Personal details</h2>
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
              <input name="id_type" value={form.id_type ?? ""} maxLength={40} onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>ID number (encrypted at rest)</span>
              <input name="id_number" value={form.id_number ?? ""} maxLength={120} autoComplete="off" onChange={updateField} />
            </label>

            <h2>Previous landlord (optional)</h2>
            <label className="manage-field">
              <span>Name</span>
              <input name="previous_landlord_name" value={form.previous_landlord_name ?? ""} maxLength={120} onChange={updateField} />
            </label>
            <label className="manage-field">
              <span>Contact details</span>
              <input name="previous_landlord_contact" value={form.previous_landlord_contact ?? ""} maxLength={120} onChange={updateField} />
            </label>
            {error && <p className="manage-error" role="alert">{error}</p>}
            {notice && <p role="status">{notice}</p>}
            <div className="manage-actions">
              <button className="manage-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : profile ? "Save profile" : "Create profile"}
              </button>
            </div>
          </form>

          <section className="manage-card">
            <h2>Identity documents</h2>
            <p>PDF, JPEG, PNG, or WebP; maximum 10 MB per file. Documents are private.</p>
            <label className="manage-field">
              <span>Upload an identity document</span>
              <input
                type="file"
                accept="application/pdf,image/jpeg,image/png,image/webp"
                disabled={!profile || uploading}
                onChange={handleUpload}
              />
            </label>
            {!profile && <p>Save your profile before adding documents.</p>}
            {uploading && <p className="manage-status">Uploading document…</p>}
            <ul className="manage-list">
              {documents.map((document) => (
                <li className="manage-card" key={document.id}>
                  <span>{document.kind} · {Math.ceil(document.file_size / 1024)} KB</span>
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
          </section>

          <section className="manage-card tenant-residences">
            <div>
              <h2>My current property</h2>
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
        </>
      )}
    </section>
  );
}

export default TenantDetailsPage;
