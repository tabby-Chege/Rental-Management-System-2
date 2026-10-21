import { useEffect, useState } from "react";
import {
  deleteTenant,
  listTenants,
  updateTenant,
} from "../../api/tenantsApi";
import { makeInternationalPhone, phoneParts, PHONE_COUNTRIES } from "../../utils/money";
import "./../ManagePropertiesPage/ManageProperties.css";

const EMPTY_FORM = { name: "", email: "", phone_code: "+254", phone_number: "" };
const PER_PAGE = 10;

function ManageTenantsPage() {
  const [tenants, setTenants] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [page, setPage] = useState(1);
  const [reloadCount, setReloadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    let ignore = false;

    async function loadTenants() {
      setLoading(true);
      setLoadError("");
      try {
        const result = await listTenants(page, PER_PAGE);
        if (!ignore) {
          setTenants(result.tenants);
          setPagination(result.pagination);
        }
      } catch (error) {
        if (!ignore) {
          setTenants([]);
          setPagination(null);
          setLoadError(error.message);
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadTenants();
    return () => {
      ignore = true;
    };
  }, [page, reloadCount]);

  function resetForm() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setFormError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!editingId) return;
    setSaving(true);
    setFormError("");
    try {
      const result = await updateTenant(editingId, {
          name: form.name,
          email: form.email,
          phone: makeInternationalPhone(form.phone_code, form.phone_number),
      });
      setTenants((current) =>
        current.map((tenant) =>
          tenant.id === result.tenant.id ? result.tenant : tenant
        )
      );
      resetForm();
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(tenant) {
    if (!window.confirm(`Delete tenant record for "${tenant.name}"?`)) return;
    try {
      await deleteTenant(tenant.id);
      if (tenants.length === 1 && page > 1) {
        setPage((current) => current - 1);
      } else {
        setReloadCount((count) => count + 1);
      }
      if (editingId === tenant.id) resetForm();
    } catch (error) {
      setLoadError(error.message);
    }
  }

  return (
    <section className="manage-properties">
      <h1>My tenants</h1>
      <p className="manage-intro">
        Tenants are added to your list through applications or leases. You can
        update contact details for existing records.
      </p>

      {editingId && <form className="manage-form" onSubmit={handleSubmit}>
        <h2>Edit tenant</h2>
        <label>
          Name *
          <input
            value={form.name}
            onChange={(event) =>
              setForm((current) => ({ ...current, name: event.target.value }))
            }
            maxLength={120}
            required
          />
        </label>
        <label>
          Email *
          <input
            type="email"
            value={form.email}
            onChange={(event) =>
              setForm((current) => ({ ...current, email: event.target.value }))
            }
            maxLength={120}
            required
          />
        </label>
        <label>
          Phone
          <div className="manage-form-row">
            <select
              aria-label="Phone country code"
              value={form.phone_code}
              onChange={(event) =>
                setForm((current) => ({ ...current, phone_code: event.target.value }))
              }
            >
              {PHONE_COUNTRIES.map(({ code, name, dialCode }) => (
                <option key={code} value={dialCode}>{name} ({dialCode})</option>
              ))}
              <option value="custom">Other (enter full international number)</option>
            </select>
            <input
              type="tel"
              value={form.phone_number}
              onChange={(event) =>
                setForm((current) => ({ ...current, phone_number: event.target.value }))
              }
              maxLength={20}
              placeholder={form.phone_code === "custom" ? "+... full number" : "712 345 678"}
            />
          </div>
        </label>
        {formError && <p className="manage-error" role="alert">{formError}</p>}
        <div className="manage-actions">
          <button className="manage-button" type="submit" disabled={saving}>
            {saving ? "Saving..." : "Save changes"}
          </button>
          {editingId && (
            <button
              className="manage-button manage-button--ghost"
              type="button"
              onClick={resetForm}
            >
              Cancel
            </button>
          )}
        </div>
      </form>}

      {loading && <p className="manage-status">Loading tenants...</p>}
      {loadError && (
        <div className="manage-status manage-status--error" role="alert">
          <p>{loadError}</p>
          <button
            className="manage-button"
            type="button"
            onClick={() => setReloadCount((count) => count + 1)}
          >
            Try again
          </button>
        </div>
      )}
      {!loading && !loadError && tenants.length === 0 && (
        <p className="manage-status">No tenant records yet.</p>
      )}
      {tenants.length > 0 && (
        <ul className="manage-list">
          {tenants.map((tenant) => (
            <li className="manage-item" key={tenant.id}>
              <div className="manage-item-info">
                <h2>{tenant.name}</h2>
                <p>{tenant.email}{tenant.phone ? ` · ${tenant.phone}` : ""}</p>
              </div>
              <div className="manage-actions">
                <button
                  className="manage-button manage-button--ghost"
                  type="button"
                  onClick={() => {
                    setEditingId(tenant.id);
                    const parsedPhone = phoneParts(tenant.phone);
                    setForm({
                      name: tenant.name,
                      email: tenant.email,
                      phone_code: parsedPhone.dialCode,
                      phone_number: parsedPhone.number,
                    });
                    setFormError("");
                  }}
                >
                  Edit
                </button>
                <button
                  className="manage-button manage-button--danger"
                  type="button"
                  onClick={() => handleDelete(tenant)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {!loading && !loadError && pagination?.pages > 1 && (
        <nav className="pagination-controls" aria-label="Tenant pages">
          <button
            type="button"
            onClick={() => setPage((current) => current - 1)}
            disabled={!pagination.has_prev}
          >
            Previous
          </button>
          <span>Page {pagination.page} of {pagination.pages}</span>
          <button
            type="button"
            onClick={() => setPage((current) => current + 1)}
            disabled={!pagination.has_next}
          >
            Next
          </button>
        </nav>
      )}
    </section>
  );
}

export default ManageTenantsPage;
