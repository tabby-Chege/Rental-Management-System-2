import { useEffect, useState } from "react";
import { getToken } from "../../api/authAPI";
import {
  createProperty,
  deleteProperty,
  listProperties,
  updateProperty,
} from "../../api/propertiesApi";
import "./ManageProperties.css";

const EMPTY_FORM = {
  name: "",
  address: "",
  city: "",
  state: "",
  zip_code: "",
  description: "",
};

function toFormValues(property) {
  return {
    name: property.name || "",
    address: property.address || "",
    city: property.city || "",
    state: property.state || "",
    zip_code: property.zip_code || "",
    description: property.description || "",
  };
}

function ManagePropertiesPage() {
  const loggedIn = Boolean(getToken());

  const [properties, setProperties] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(loggedIn);
  const [loadError, setLoadError] = useState(null);
  const [reloadCount, setReloadCount] = useState(0);

  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    if (!loggedIn) return undefined;

    let ignore = false; // stops an old request from overwriting a newer one

    listProperties({ page })
      .then((data) => {
        if (!ignore) {
          setProperties(data.properties);
          setPagination(data.pagination);
          setLoadError(null);
        }
      })
      .catch((err) => {
        if (!ignore) setLoadError(err.message);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [loggedIn, page, reloadCount]);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  function resetForm() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setFormError(null);
  }

  function handleEdit(property) {
    setEditingId(property.id);
    setForm(toFormValues(property));
    setFormError(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);

    try {
      if (editingId) {
        const updated = await updateProperty(editingId, form);
        setProperties((current) =>
          current.map((p) => (p.id === updated.id ? updated : p))
        );
      } else {
        const created = await createProperty(form);
        if (page !== 1) {
          setPage(1);
        } else {
          setProperties((current) => [created, ...current].slice(0, 10));
          setReloadCount((count) => count + 1);
        }
      }
      resetForm();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(property) {
    const confirmed = window.confirm(
      `Delete "${property.name}"? This cannot be undone.`
    );
    if (!confirmed) return;

    try {
      await deleteProperty(property.id);
      if (editingId === property.id) resetForm();
      if (properties.length === 1 && page > 1) {
        setPage((current) => current - 1);
      } else {
        handleRetry();
      }
    } catch (err) {
      setLoadError(err.message);
    }
  }

  function handleRetry() {
    setLoading(true);
    setLoadError(null);
    setReloadCount((count) => count + 1);
  }

  if (!loggedIn) {
    return (
      <section className="manage-properties">
        <h1>My properties</h1>
        <p className="manage-status">Please log in to manage your properties.</p>
      </section>
    );
  }

  return (
    <section className="manage-properties">
      <h1>My properties</h1>
      <p className="manage-intro">
        Add, edit, and remove the properties you manage.
      </p>

      <form className="manage-form" onSubmit={handleSubmit}>
        <h2>{editingId ? "Edit property" : "Add a property"}</h2>

        <label>
          Name *
          <input
            name="name"
            value={form.name}
            onChange={handleChange}
            maxLength={120}
            required
          />
        </label>

        <label>
          Address *
          <input
            name="address"
            value={form.address}
            onChange={handleChange}
            maxLength={255}
            required
          />
        </label>

        <div className="manage-form-row">
          <label>
            City *
            <input
              name="city"
              value={form.city}
              onChange={handleChange}
              maxLength={100}
              required
            />
          </label>
          <label>
            State / County *
            <input
              name="state"
              value={form.state}
              onChange={handleChange}
              maxLength={100}
              required
            />
          </label>
          <label>
            ZIP / Postal code
            <input
              name="zip_code"
              value={form.zip_code}
              onChange={handleChange}
              maxLength={20}
            />
          </label>
        </div>

        <label>
          Description
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={3}
          />
        </label>

        {formError && (
          <p className="manage-error" role="alert">
            {formError}
          </p>
        )}

        <div className="manage-actions">
          <button type="submit" className="manage-button" disabled={saving}>
            {saving ? "Saving..." : editingId ? "Save changes" : "Add property"}
          </button>
          {editingId && (
            <button
              type="button"
              className="manage-button manage-button--ghost"
              onClick={resetForm}
            >
              Cancel
            </button>
          )}
        </div>
      </form>

      {loading && <p className="manage-status">Loading properties...</p>}

      {loadError && (
        <div className="manage-status manage-status--error" role="alert">
          <p>{loadError}</p>
          <button type="button" className="manage-button" onClick={handleRetry}>
            Try again
          </button>
        </div>
      )}

      {!loading && !loadError && properties.length === 0 && (
        <p className="manage-status">
          You have no properties yet. Add your first one above.
        </p>
      )}

      {properties.length > 0 && (
        <ul className="manage-list">
          {properties.map((property) => (
            <li key={property.id} className="manage-item">
              <div className="manage-item-info">
                <h3>{property.name}</h3>
                <p>
                  {property.address}, {property.city}, {property.state}
                  {property.zip_code ? ` ${property.zip_code}` : ""}
                </p>
                {property.description && (
                  <p className="manage-item-description">
                    {property.description}
                  </p>
                )}
                {!loading && !loadError && pagination?.pages > 1 && (
                  <nav className="pagination-controls" aria-label="Property pages">
                    <button
                      type="button"
                      onClick={() => setPage((current) => current - 1)}
                      disabled={!pagination.has_prev}
                    >
                      Previous
                    </button>
                    <span>
                      Page {pagination.page} of {pagination.pages} ({pagination.total} total)
                    </span>
                    <button
                      type="button"
                      onClick={() => setPage((current) => current + 1)}
                      disabled={!pagination.has_next}
                    >
                      Next
                    </button>
                  </nav>
                )}
              </div>
              <div className="manage-actions">
                <button
                  type="button"
                  className="manage-button manage-button--ghost"
                  onClick={() => handleEdit(property)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="manage-button manage-button--danger"
                  onClick={() => handleDelete(property)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default ManagePropertiesPage;
