import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createLease, deleteLease, listLeases, updateLease } from "../../api/leasesAPI";
import { listTenants } from "../../api/tenantsApi";
import { listProperties, listUnits } from "../../api/unitsAPI";
import { validateLeaseForm } from "../../utils/leaseForm";
import { CURRENCY_CODES, currencyPrecision, formatMoney } from "../../utils/money";
import "../manage.css";

const STATUSES = ["active", "ended", "terminated"];
const EMPTY_FORM = {
  unit_id: "",
  tenant_id: "",
  start_date: "",
  end_date: "",
  monthly_rent: "",
  deposit: "",
  status: "active",
};

function describeUnit(unit, properties) {
  const property = properties.find((p) => p.id === unit.property_id);
  return `Unit ${unit.unit_number}, ${property ? property.name : `property #${unit.property_id}`}`;
}

function leaseToForm(lease) {
  return {
    unit_id: String(lease.unit_id),
    tenant_id: String(lease.tenant_id),
    start_date: lease.start_date,
    end_date: lease.end_date,
    monthly_rent: lease.monthly_rent,
    deposit: lease.deposit ?? "",
    status: lease.status,
    currency: lease.currency,
  };
}

// unit_id is only sent on create: to move a tenant, end the lease and add a new one.
function toBody(form, isEdit) {
  const body = {
    tenant_id: Number(form.tenant_id),
    start_date: form.start_date,
    end_date: form.end_date,
    monthly_rent: Number(form.monthly_rent),
    deposit: String(form.deposit).trim() === "" ? 0 : Number(form.deposit),
    status: form.status,
  };
  if (!isEdit) body.unit_id = Number(form.unit_id);
  return body;
}

function Field({ label, error, children }) {
  return (
    <label className="manage-field">
      <span>{label}</span>
      {children}
      {error && <small className="manage-error">{error}</small>}
    </label>
  );
}

function LeaseForm({ initial, units, properties, tenants, isEdit, submitLabel, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const currency =
    units.find((unit) => String(unit.id) === String(form.unit_id))?.currency
    || initial.currency
    || CURRENCY_CODES[0];

  function handleChange(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validateLeaseForm(form, { requireUnit: !isEdit, currency });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setIsSaving(true);
    setSubmitError("");
    try {
      await onSubmit(toBody(form, isEdit));
      if (!isEdit) setForm(EMPTY_FORM);
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setIsSaving(false);
    }
  }

  const invalid = (name) => Boolean(errors[name]);

  return (
    <form className="manage-form" onSubmit={handleSubmit} noValidate>
      {!isEdit && (
        <Field label="Unit" error={errors.unit_id}>
          <select name="unit_id" value={form.unit_id} onChange={handleChange} aria-invalid={invalid("unit_id")}>
            <option value="">Choose a unit</option>
            {units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {describeUnit(unit, properties)}
              </option>
            ))}
          </select>
        </Field>
      )}
      <Field label="Tenant" error={errors.tenant_id}>
        <select name="tenant_id" value={form.tenant_id} onChange={handleChange} aria-invalid={invalid("tenant_id")}>
          <option value="">Choose a tenant</option>
          {tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Start date" error={errors.start_date}>
        <input type="date" name="start_date" value={form.start_date} onChange={handleChange} aria-invalid={invalid("start_date")} />
      </Field>
      <Field label="End date" error={errors.end_date}>
        <input type="date" name="end_date" value={form.end_date} onChange={handleChange} aria-invalid={invalid("end_date")} />
      </Field>
      <Field label={`Monthly rent (${currency})`} error={errors.monthly_rent}>
        <input type="number" min="0" step={10 ** -currencyPrecision(currency)} name="monthly_rent" value={form.monthly_rent} onChange={handleChange} aria-invalid={invalid("monthly_rent")} />
      </Field>
      <Field label={`Deposit (${currency}, optional)`} error={errors.deposit}>
        <input type="number" min="0" step={10 ** -currencyPrecision(currency)} name="deposit" value={form.deposit} onChange={handleChange} aria-invalid={invalid("deposit")} />
      </Field>
      <Field label="Status" error={errors.status}>
        <select name="status" value={form.status} onChange={handleChange}>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </option>
          ))}
        </select>
      </Field>
      {submitError && (
        <p className="manage-error" role="alert">
          {submitError}
        </p>
      )}
      <div className="manage-actions">
        <button type="submit" className="manage-button" disabled={isSaving}>
          {isSaving ? "Saving…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="manage-button is-secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

function LeasesPage() {
  const [searchParams] = useSearchParams();
  const [leases, setLeases] = useState([]);
  const [units, setUnits] = useState([]);
  const [properties, setProperties] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(Boolean(searchParams.get("unit_id")));
  const [notice, setNotice] = useState("");
  const [editingId, setEditingId] = useState(null);
  const initialForm = {
    ...EMPTY_FORM,
    unit_id: searchParams.get("unit_id") ?? "",
    tenant_id: searchParams.get("tenant_id") ?? "",
    start_date: searchParams.get("start_date") ?? "",
    monthly_rent: searchParams.get("monthly_rent") ?? "",
  };

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        const [leaseList, unitList, tenantList, propertyList] = await Promise.all([
          listLeases(),
          listUnits(),
          listTenants().then((result) => result.tenants),
          listProperties().catch(() => []), // only used for labels
        ]);
        if (!ignore) {
          setLeases(leaseList);
          setUnits(unitList);
          setTenants(tenantList);
          setProperties(propertyList);
        }
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

  const unitLabel = (id) => {
    const unit = units.find((u) => u.id === id);
    return unit ? describeUnit(unit, properties) : `Unit #${id}`;
  };
  const tenantName = (id) => tenants.find((t) => t.id === id)?.name ?? `Tenant #${id}`;

  async function handleCreate(body) {
    const created = await createLease(body);
    setLeases((current) => [created, ...current]);
    setCreateOpen(false);
    setNotice("Lease created and added to your lease list.");
  }

  async function handleUpdate(id, body) {
    const updated = await updateLease(id, body);
    setLeases((current) => current.map((l) => (l.id === id ? updated : l)));
    setEditingId(null);
  }

  async function handleEnd(lease) {
    setError("");
    try {
      await handleUpdate(lease.id, { status: "ended" });
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(lease) {
    if (!window.confirm("Delete this lease? This cannot be undone.")) return;
    setError("");
    try {
      await deleteLease(lease.id);
      setLeases((current) => current.filter((l) => l.id !== lease.id));
    } catch (err) {
      setError(err.message);
    }
  }

  const editingLease = leases.find((lease) => lease.id === editingId);
  const canAdd = units.length > 0 && tenants.length > 0;

  return (
    <section className="manage-page">
      <header className="manage-page-heading">
        <div>
          <h1>Leases</h1>
          <p className="manage-status">Review current rental agreements and keep lease terms up to date.</p>
        </div>
        {!isLoading && canAdd && (
          <button type="button" className="manage-button" onClick={() => {
            setError("");
            setNotice("");
            setCreateOpen(true);
          }}>
            Add lease
          </button>
        )}
      </header>

      {isLoading && <p className="manage-status">Loading…</p>}
      {!isLoading && units.length === 0 && (
        <p className="manage-status">Add a unit first on the Units page.</p>
      )}
      {!isLoading && units.length > 0 && tenants.length === 0 && (
        <p className="manage-status">A tenant must apply for a property before a lease can be created.</p>
      )}

      {createOpen && canAdd && (
        <div className="manage-dialog-backdrop">
          <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="lease-dialog-title">
            <div className="manage-dialog-heading">
              <div>
                <h2 id="lease-dialog-title">Add a lease</h2>
                <p>Choose a unit and tenant, then enter the agreement terms.</p>
              </div>
              <button type="button" className="manage-dialog-close" aria-label="Close lease form" onClick={() => setCreateOpen(false)}>×</button>
            </div>
            <LeaseForm
              key={searchParams.toString()}
              initial={initialForm}
              units={units}
              properties={properties}
              tenants={tenants}
              submitLabel="Add lease"
              onSubmit={handleCreate}
              onCancel={() => setCreateOpen(false)}
            />
          </section>
        </div>
      )}

      {error && (
        <p className="manage-error" role="alert">
          {error}
        </p>
      )}
      {notice && <p className="manage-status" role="status">{notice}</p>}
      {!isLoading && leases.length === 0 && !error && (
        <p className="manage-status">No leases yet.</p>
      )}

      {editingLease && (
        <div className="manage-dialog-backdrop">
          <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="edit-lease-dialog-title">
            <div className="manage-dialog-heading">
              <div>
                <h2 id="edit-lease-dialog-title">Edit lease</h2>
                <p>Update the tenant and agreement terms for this lease.</p>
              </div>
              <button type="button" className="manage-dialog-close" aria-label="Close lease editor" onClick={() => setEditingId(null)}>×</button>
            </div>
            <LeaseForm
              initial={leaseToForm(editingLease)}
              units={units}
              properties={properties}
              tenants={tenants}
              isEdit
              submitLabel="Save changes"
              onSubmit={(body) => handleUpdate(editingLease.id, body)}
              onCancel={() => setEditingId(null)}
            />
          </section>
        </div>
      )}

      <ul className="manage-list">
        {leases.map((lease) => (
          <li key={lease.id} className="manage-card">
              <>
                <div>
                  <strong>{unitLabel(lease.unit_id)}</strong>
                  <span className={`manage-badge is-${lease.status}`}>
                    {lease.status.charAt(0).toUpperCase() + lease.status.slice(1)}
                  </span>
                  <p>{tenantName(lease.tenant_id)}</p>
                  <p>
                    {lease.start_date} to {lease.end_date}
                  </p>
                  <p>
                    Rent {formatMoney(lease.monthly_rent, lease.currency)} per month, deposit {formatMoney(lease.deposit, lease.currency)}
                  </p>
                </div>
                <div className="manage-actions">
                  <button
                    type="button"
                    className="manage-button is-secondary"
                    onClick={() => setEditingId(lease.id)}
                  >
                    Edit
                  </button>
                  {lease.status === "active" && (
                    <button
                      type="button"
                      className="manage-button is-secondary"
                      onClick={() => handleEnd(lease)}
                    >
                      End lease
                    </button>
                  )}
                  <button
                    type="button"
                    className="manage-button is-danger"
                    onClick={() => handleDelete(lease)}
                  >
                    Delete
                  </button>
                </div>
              </>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default LeasesPage;
