import { useEffect, useState } from "react";
import { createUnit, deleteUnit, listProperties, listUnits, updateUnit } from "../../api/unitsAPI";
import { validateUnitForm } from "../../utils/unitForm";
import "../manage.css";

const EMPTY_FORM = { property_id: "", unit_number: "", bedrooms: "", bathrooms: "", rent_amount: "" };
const CREATE_FIELDS = ["property_id", "unit_number", "bedrooms", "bathrooms", "rent_amount"];
// A unit cannot move to another property, so property_id is create-only.
const EDIT_FIELDS = ["unit_number", "bedrooms", "bathrooms", "rent_amount"];

const FIELD_CONFIG = {
  property_id: { label: "Property" },
  unit_number: { label: "Unit number", type: "text" },
  bedrooms: { label: "Bedrooms (optional)", type: "number", min: "0" },
  bathrooms: { label: "Bathrooms (optional)", type: "number", min: "0", step: "0.5" },
  rent_amount: { label: "Listed rent (optional)", type: "number", min: "0", step: "0.01" },
};

const money = (value) =>
  Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function unitToForm(unit) {
  return {
    ...EMPTY_FORM,
    unit_number: unit.unit_number,
    bedrooms: unit.bedrooms ?? "",
    bathrooms: unit.bathrooms ?? "",
    rent_amount: unit.rent_amount ?? "",
  };
}

// Empty optional fields become null so editing can clear them.
function toBody(form, fields) {
  const body = {};
  fields.forEach((name) => {
    const value = String(form[name] ?? "").trim();
    if (name === "unit_number") body[name] = value;
    else if (name === "property_id") body[name] = Number(value);
    else body[name] = value === "" ? null : Number(value);
  });
  return body;
}

function unitDetails(unit) {
  const parts = [];
  if (unit.bedrooms != null) parts.push(`${unit.bedrooms} bed`);
  if (unit.bathrooms != null) parts.push(`${unit.bathrooms} bath`);
  if (unit.rent_amount != null) parts.push(`listed rent ${money(unit.rent_amount)}`);
  return parts.length > 0 ? parts.join(", ") : "No extra details added";
}

function UnitForm({ initial, fields, properties = [], submitLabel, resetOnSave, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  function handleChange(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validateUnitForm(form, { requireProperty: fields.includes("property_id") });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setIsSaving(true);
    setSubmitError("");
    try {
      await onSubmit(toBody(form, fields));
      if (resetOnSave) setForm(EMPTY_FORM);
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form className="manage-form" onSubmit={handleSubmit} noValidate>
      {fields.map((name) => {
        const config = FIELD_CONFIG[name];
        return (
          <label key={name} className="manage-field">
            <span>{config.label}</span>
            {name === "property_id" ? (
              <select
                name={name}
                value={form[name]}
                onChange={handleChange}
                aria-invalid={Boolean(errors[name])}
              >
                <option value="">Choose a property</option>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.name}, {property.city}
                  </option>
                ))}
              </select>
            ) : (
              <input
                name={name}
                type={config.type}
                min={config.min}
                step={config.step}
                value={form[name]}
                onChange={handleChange}
                aria-invalid={Boolean(errors[name])}
              />
            )}
            {errors[name] && <small className="manage-error">{errors[name]}</small>}
          </label>
        );
      })}
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

function UnitsPage() {
  const [units, setUnits] = useState([]);
  const [properties, setProperties] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        const [unitList, propertyList] = await Promise.all([listUnits(), listProperties()]);
        if (!ignore) {
          setUnits(unitList);
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

  const propertyName = (id) => properties.find((p) => p.id === id)?.name ?? `Property #${id}`;

  async function handleCreate(body) {
    const created = await createUnit(body);
    setUnits((current) => [...current, created]);
  }

  async function handleUpdate(id, body) {
    const updated = await updateUnit(id, body);
    setUnits((current) => current.map((u) => (u.id === id ? updated : u)));
    setEditingId(null);
  }

  async function handleDelete(unit) {
    if (!window.confirm(`Delete unit ${unit.unit_number}? This cannot be undone.`)) return;
    setError("");
    try {
      await deleteUnit(unit.id);
      setUnits((current) => current.filter((u) => u.id !== unit.id));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="manage-page">
      <h1>Units</h1>

      <div className="manage-card">
        <h2>Add a unit</h2>
        {!isLoading && properties.length === 0 ? (
          <p className="manage-status">Add a property first, then come back to add its units.</p>
        ) : (
          <UnitForm
            initial={EMPTY_FORM}
            fields={CREATE_FIELDS}
            properties={properties}
            submitLabel="Add unit"
            resetOnSave
            onSubmit={handleCreate}
          />
        )}
      </div>

      {error && (
        <p className="manage-error" role="alert">
          {error}
        </p>
      )}
      {isLoading && <p className="manage-status">Loading units…</p>}
      {!isLoading && units.length === 0 && !error && (
        <p className="manage-status">No units yet. Add your first one above.</p>
      )}

      <ul className="manage-list">
        {units.map((unit) => (
          <li key={unit.id} className="manage-card">
            {editingId === unit.id ? (
              <UnitForm
                initial={unitToForm(unit)}
                fields={EDIT_FIELDS}
                submitLabel="Save changes"
                onSubmit={(body) => handleUpdate(unit.id, body)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <>
                <div>
                  <strong>Unit {unit.unit_number}</strong>
                  <span className={`manage-badge ${unit.is_occupied ? "is-occupied" : "is-vacant"}`}>
                    {unit.is_occupied ? "Occupied" : "Vacant"}
                  </span>
                  <p>{propertyName(unit.property_id)}</p>
                  <p>{unitDetails(unit)}</p>
                </div>
                <div className="manage-actions">
                  <button
                    type="button"
                    className="manage-button is-secondary"
                    onClick={() => setEditingId(unit.id)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="manage-button is-danger"
                    onClick={() => handleDelete(unit)}
                  >
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

export default UnitsPage;
