import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createUnit, deleteUnit, listProperties, listUnits, updateUnit } from "../../api/unitsAPI";
import { formatBedroomCount, formatUnitType, validateUnitForm } from "../../utils/unitForm";
import "../manage.css";

const EMPTY_FORM = {
  property_id: "",
  unit_number: "",
  unit_type: "",
  bedrooms: "",
  bathrooms: "",
  rent_amount: "",
  description: "",
  availability_status: "vacant",
};
const CREATE_FIELDS = [
  "property_id",
  "unit_number",
  "unit_type",
  "bedrooms",
  "bathrooms",
  "rent_amount",
  "description",
];
// A unit cannot move to another property, so property_id is create-only.
const EDIT_FIELDS = ["unit_number", "unit_type", "bedrooms", "bathrooms", "rent_amount", "description"];

const FIELD_CONFIG = {
  property_id: { label: "Property" },
  unit_number: { label: "Unit number", type: "text" },
  unit_type: { label: "Unit type", type: "select" },
  bedrooms: { label: "Bedrooms (0 for studio/bedsitter)", type: "number", min: "0", step: "1" },
  bathrooms: { label: "Bathrooms", type: "number", min: "0", max: "99.9", step: "0.5" },
  rent_amount: { label: "Monthly rent (KES)", type: "number", min: "0.01", max: "99999999.99", step: "0.01" },
  description: { label: "Unit description (optional)", type: "textarea" },
};

const money = (value) =>
  Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function unitToForm(unit) {
  return {
    ...EMPTY_FORM,
    unit_number: unit.unit_number,
    unit_type: unit.unit_type ?? "",
    bedrooms: unit.bedrooms ?? "",
    bathrooms: unit.bathrooms ?? "",
    rent_amount: unit.rent_amount ?? "",
    description: unit.description ?? "",
    availability_status: unit.availability_status ?? (unit.is_occupied ? "occupied" : "vacant"),
  };
}

// Empty optional fields become null so editing can clear them.
function toBody(form, fields) {
  const body = {};
  fields.forEach((name) => {
    const value = String(form[name] ?? "").trim();
    if (name === "unit_number" || name === "unit_type" || name === "description") {
      body[name] = value || null;
    }
    else if (name === "property_id") body[name] = Number(value);
    else body[name] = value === "" ? null : Number(value);
  });
  return body;
}

function unitDetails(unit) {
  const parts = [];
  parts.push(formatUnitType(unit.unit_type, unit.bedrooms));
  parts.push(formatBedroomCount(unit.bedrooms));
  if (unit.bathrooms != null) parts.push(`${unit.bathrooms} bath`);
  if (unit.rent_amount != null) parts.push(`KES ${money(unit.rent_amount)} per month`);
  return parts.length > 0 ? parts.join(", ") : "No extra details added";
}

function UnitForm({
  initial,
  fields,
  properties = [],
  submitLabel,
  resetOnSave,
  onSubmit,
  onCancel,
  onPropertyChange,
}) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
    if (name === "property_id") onPropertyChange?.(value);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validateUnitForm(form, {
      requireProperty: fields.includes("property_id"),
      requireDetails: true,
    });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setIsSaving(true);
    setSubmitError("");
    try {
      await onSubmit(toBody(form, fields));
      if (resetOnSave) {
        setForm({ ...EMPTY_FORM, property_id: form.property_id });
      }
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
            ) : config.type === "select" ? (
              <select
                name={name}
                value={form[name]}
                onChange={handleChange}
                aria-invalid={Boolean(errors[name])}
              >
                <option value="">Choose a unit type</option>
                <option value="bedsitter">Bedsitter</option>
                <option value="studio">Studio</option>
                <option value="one-bedroom">One bedroom</option>
                <option value="two-bedroom">Two bedrooms</option>
                <option value="three-bedroom">Three bedrooms</option>
                <option value="four-bedroom">Four bedrooms</option>
                <option value="other">Other</option>
              </select>
            ) : config.type === "textarea" ? (
              <textarea
                name={name}
                value={form[name]}
                onChange={handleChange}
                maxLength={5000}
                rows={3}
                aria-invalid={Boolean(errors[name])}
              />
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
      <div className="manage-field">
        <span>Availability</span>
        <strong>{initial.availability_status === "occupied" ? "Occupied" : "Vacant"}</strong>
        <small>Availability is based on active lease dates and cannot be set independently.</small>
      </div>
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
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedPropertyId = searchParams.get("property_id") || "";
  const [units, setUnits] = useState([]);
  const [properties, setProperties] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null);

  useEffect(() => {
    let ignore = false;
    async function load() {
      setIsLoading(true);
      setError("");
      try {
        const [unitList, propertyList] = await Promise.all([
          listUnits(selectedPropertyId || undefined),
          listProperties(),
        ]);
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
  }, [selectedPropertyId]);

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
            initial={{
              ...EMPTY_FORM,
              property_id: selectedPropertyId,
            }}
            fields={CREATE_FIELDS}
            properties={properties}
            onPropertyChange={(propertyId) => {
              if (propertyId) setSearchParams({ property_id: propertyId });
              else setSearchParams({});
            }}
            submitLabel="Add unit"
            resetOnSave
            onSubmit={handleCreate}
          />
        )}
      </div>

      {selectedPropertyId && properties.some((property) => String(property.id) === selectedPropertyId) && (
        <button
          type="button"
          className="manage-button is-secondary"
          onClick={() => setSearchParams({})}
        >
          Show units for all properties
        </button>
      )}

      {error && (
        <p className="manage-error" role="alert">
          {error}
        </p>
      )}
      {isLoading && <p className="manage-status">Loading units…</p>}
      {!isLoading && units.length === 0 && !error && (
        <p className="manage-status">
          {selectedPropertyId ? "This property has no units yet. Add its first unit above." : "No units yet. Add your first one above."}
        </p>
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
