import { useEffect, useState } from "react";
import { getCurrentUser } from "../../api/authAPI";
import { listMyLeases } from "../../api/leasesAPI";
import {
  createMaintenanceRequest,
  downloadPrivateFile,
  listMaintenanceRequests,
  updateMaintenanceStatus,
  uploadMaintenancePhoto,
} from "../../api/landlordToolsApi";
import "../manage.css";

const STATUS_LABELS = {
  submitted: "Submitted",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

function MaintenancePage() {
  const [user, setUser] = useState(null);
  const [leases, setLeases] = useState([]);
  const [requests, setRequests] = useState([]);
  const [form, setForm] = useState({ lease_id: "", title: "", description: "" });
  const [files, setFiles] = useState([]);
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        const [{ user: currentUser }, requestList] = await Promise.all([
          getCurrentUser(),
          listMaintenanceRequests(),
        ]);
        const leaseList = currentUser.role === "tenant"
          ? await listMyLeases()
          : [];
        if (!ignore) {
          setUser(currentUser);
          setRequests(requestList);
          setLeases(leaseList.filter((lease) => lease.status === "active"));
          setForm((current) => ({
            ...current,
            lease_id: current.lease_id || String(leaseList[0]?.id ?? ""),
          }));
        }
      } catch (requestError) {
        if (!ignore) setError(requestError.message);
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setSaving(true);
    let createdRequestId = null;
    try {
      const created = await createMaintenanceRequest({
        lease_id: Number(form.lease_id),
        title: form.title,
        description: form.description,
      });
      createdRequestId = created.id;
      setRequests((current) => [created, ...current]);
      const selectedFiles = files;
      setForm((current) => ({ ...current, title: "", description: "" }));
      setFiles([]);
      setFormOpen(false);
      setNotice("Maintenance request submitted.");
      for (const file of selectedFiles) {
        const result = await uploadMaintenancePhoto(created.id, file);
        setRequests((current) =>
          current.map((item) =>
            item.id === created.id
              ? { ...item, photos: [...(item.photos ?? []), result.photo] }
              : item,
          ),
        );
      }
    } catch (requestError) {
      setError(
        createdRequestId
          ? `Request #${createdRequestId} was submitted, but a photo could not be uploaded: ${requestError.message}`
          : requestError.message,
      );
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(item, status) {
    setError("");
    try {
      const updated = await updateMaintenanceStatus(item.id, status);
      setRequests((current) =>
        current.map((requestItem) =>
          requestItem.id === updated.id ? updated : requestItem,
        ),
      );
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function downloadPhoto(photo) {
    setError("");
    try {
      await downloadPrivateFile(photo.download_url, `maintenance-${photo.id}`);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <section className="manage-page">
      <header>
        <h1>Maintenance</h1>
        <p className="manage-status">
          Submit repairs and follow progress with the property manager.
        </p>
        {user?.role === "tenant" && leases.length > 0 && (
          <button type="button" className="manage-button" onClick={() => {
            setError("");
            setNotice("");
            setFormOpen(true);
          }}>
            Report an issue
          </button>
        )}
      </header>
      {error && <p className="manage-error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {loading ? (
        <p className="manage-status">Loading maintenance requests…</p>
      ) : (
        <>
          {user?.role === "tenant" && (
            leases.length === 0 ? (
              <p className="manage-status">You need an active lease to submit a maintenance request.</p>
            ) : formOpen && (
              <div className="manage-dialog-backdrop">
                <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="maintenance-dialog-title">
                  <div className="manage-dialog-heading">
                    <div>
                      <h2 id="maintenance-dialog-title">Report a maintenance issue</h2>
                      <p>Describe the repair needed and attach photos if helpful.</p>
                    </div>
                    <button type="button" className="manage-dialog-close" aria-label="Close maintenance form" disabled={saving} onClick={() => setFormOpen(false)}>×</button>
                  </div>
                  <form className="manage-form" onSubmit={handleSubmit}>
                <>
                  <label className="manage-field">
                    <span>Rental</span>
                    <select
                      required
                      value={form.lease_id}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, lease_id: event.target.value }))
                      }
                    >
                      {leases.map((lease) => (
                        <option value={lease.id} key={lease.id}>
                          Lease #{lease.id} · Unit #{lease.unit_id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="manage-field">
                    <span>Issue</span>
                    <input
                      required
                      maxLength={160}
                      value={form.title}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, title: event.target.value }))
                      }
                    />
                  </label>
                  <label className="manage-field">
                    <span>Description</span>
                    <textarea
                      required
                      maxLength={5000}
                      rows={4}
                      value={form.description}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          description: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="manage-field">
                    <span>Photos (JPEG, PNG, WebP; max 10 MB each)</span>
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      multiple
                      onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                    />
                  </label>
                  <button className="manage-button" type="submit" disabled={saving}>
                    {saving ? "Submitting…" : "Submit request"}
                  </button>
                </>
                  </form>
                </section>
              </div>
            )
          )}
          {requests.length === 0 ? (
            <p className="manage-status">No maintenance requests yet.</p>
          ) : (
            <ul className="manage-list">
              {requests.map((item) => (
                <li className="manage-card" key={item.id}>
                  <div>
                    <strong>{item.title}</strong>
                    <span className={`manage-badge is-${item.status}`}>
                      {STATUS_LABELS[item.status]}
                    </span>
                    <p>{item.property_name} · Unit {item.unit_number}</p>
                    <p>{item.description}</p>
                    <small>Submitted {new Date(item.created_at).toLocaleString()}</small>
                    {item.photos?.length > 0 && (
                      <div className="manage-actions">
                        {item.photos.map((photo) => (
                          <button
                            className="manage-button is-secondary"
                            type="button"
                            key={photo.id}
                            onClick={() => downloadPhoto(photo)}
                          >
                            Download photo ({Math.ceil(photo.file_size / 1024)} KB)
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {user?.role === "landlord" || user?.role === "admin" ? (
                    <label className="manage-field">
                      <span>Update status</span>
                      <select
                        value={item.status}
                        onChange={(event) => changeStatus(item, event.target.value)}
                      >
                        {Object.entries(STATUS_LABELS).map(([value, label]) => (
                          <option value={value} key={value}>{label}</option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <span className={`manage-badge is-${item.status}`}>
                      {STATUS_LABELS[item.status]}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

export default MaintenancePage;
