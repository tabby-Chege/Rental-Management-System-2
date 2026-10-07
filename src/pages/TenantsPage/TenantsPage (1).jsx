import { useEffect, useState } from "react";
import {
  createTenant,
  deleteTenant,
  getCurrentUser,
  getMyTenant,
  getToken,
  listTenants,
  updateTenant,
} from "../../api/tenantsAPI";
import { validateTenantForm } from "../../utils/tenantForm";
import "./TenantsPage.css";

const EMPTY_FORM = { name: "", email: "", phone: "" };
const MANAGER_ROLES = ["landlord", "admin"];

function TenantsPage() {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    async function load() {
      if (!getToken()) {
        setError("Please log in to view tenant information.");
        setIsLoading(false);
        return;
      }
      try {
        const me = await getCurrentUser();
        if (!ignore) setUser(me);
      } catch (err) {
        if (!ignore) setError(err.message);
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  if (isLoading) return <p className="tenants-status">Loading…</p>;
  if (error) return <p className="tenants-status tenants-error" role="alert">{error}</p>;
  if (MANAGER_ROLES.includes(user.role)) return <ManagerView />;
  return <TenantView />;
}

function TenantForm({ initial, onSubmit, onCancel, submitLabel, fields, requireName }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  function handleChange(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validateTenantForm(form, { requireName });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setIsSaving(true);
    setSubmitError("");
    try {
      const body = {};
      fields.forEach((field) => {
        body[field] = form[field].trim();
      });
      await onSubmit(body);
      if (!initial.id) setForm(EMPTY_FORM);
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setIsSaving(false);
    }
  }

  const labels = { name: "Full name", email: "Email", phone: "Phone" };

  return (
    <form className="tenant-form" onSubmit={handleSubmit} noValidate>
      {fields.map((field) => (
        <label key={field} className="tenant-field">
          <span>{labels[field]}</span>
          <input
            name={field}
            type={field === "email" ? "email" : "text"}
            value={form[field]}
            onChange={handleChange}
            aria-invalid={Boolean(errors[field])}
          />
          {errors[field] && <small className="tenants-error">{errors[field]}</small>}
        </label>
      ))}
      {submitError && <p className="tenants-error" role="alert">{submitError}</p>}
      <div className="tenant-form-actions">
        <button type="submit" className="tenant-button" disabled={isSaving}>
          {isSaving ? "Saving…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="tenant-button is-secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

function ManagerView() {
  const [tenants, setTenants] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        const data = await listTenants();
        if (!ignore) setTenants(data);
      } catch (err) {
        if (!ignore) setError(err.message);
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleCreate(body) {
    const created = await createTenant(body);
    setTenants((current) => [...current, created].sort((a, b) => a.name.localeCompare(b.name)));
  }

  async function handleUpdate(id, body) {
    const updated = await updateTenant(id, body);
    setTenants((current) => current.map((t) => (t.id === id ? updated : t)));
    setEditingId(null);
  }

  async function handleDelete(tenant) {
    if (!window.confirm(`Delete ${tenant.name}? This cannot be undone.`)) return;
    setError("");
    try {
      await deleteTenant(tenant.id);
      setTenants((current) => current.filter((t) => t.id !== tenant.id));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="tenants-page">
      <h1>Tenants</h1>

      <div className="tenants-card">
        <h2>Add a tenant</h2>
        <TenantForm
          initial={EMPTY_FORM}
          fields={["name", "email", "phone"]}
          requireName
          submitLabel="Add tenant"
          onSubmit={handleCreate}
        />
      </div>

      {error && <p className="tenants-error" role="alert">{error}</p>}
      {isLoading && <p className="tenants-status">Loading tenants…</p>}
      {!isLoading && tenants.length === 0 && !error && (
        <p className="tenants-status">No tenants yet. Add your first one above.</p>
      )}

      <ul className="tenant-list">
        {tenants.map((tenant) => (
          <li key={tenant.id} className="tenants-card">
            {editingId === tenant.id ? (
              <TenantForm
                initial={{ ...tenant, phone: tenant.phone ?? "" }}
                fields={["name", "email", "phone"]}
                requireName
                submitLabel="Save changes"
                onSubmit={(body) => handleUpdate(tenant.id, body)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <>
                <div>
                  <strong>{tenant.name}</strong>
                  <p>{tenant.email}</p>
                  <p>{tenant.phone || "No phone on file"}</p>
                </div>
                <div className="tenant-form-actions">
                  <button className="tenant-button is-secondary" onClick={() => setEditingId(tenant.id)}>
                    Edit
                  </button>
                  <button className="tenant-button is-danger" onClick={() => handleDelete(tenant)}>
                    Delete
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function TenantView() {
  const [tenant, setTenant] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        const mine = await getMyTenant();
        if (!ignore) setTenant(mine);
      } catch (err) {
        if (!ignore) setError(err.message);
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleUpdate(body) {
    setSaved(false);
    setTenant(await updateTenant(tenant.id, body));
    setSaved(true);
  }

  if (isLoading) return <p className="tenants-status">Loading your details…</p>;
  if (error) return <p className="tenants-status tenants-error" role="alert">{error}</p>;

  return (
    <section className="tenants-page">
      <h1>My details</h1>
      <div className="tenants-card">
        <p><strong>{tenant.name}</strong></p>
        <p className="tenants-status">Your landlord manages your name. You can update your contact details below.</p>
        <TenantForm
          initial={{ ...tenant, phone: tenant.phone ?? "" }}
          fields={["email", "phone"]}
          requireName={false}
          submitLabel="Save contact details"
          onSubmit={handleUpdate}
        />
        {saved && <p role="status">Contact details updated.</p>}
      </div>
    </section>
  );
}

export default TenantsPage;
