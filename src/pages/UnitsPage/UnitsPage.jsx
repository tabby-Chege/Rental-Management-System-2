import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  bulkCreateUnits,
  createRoom,
  createUnit,
  deleteRoom,
  deleteUnit,
  listProperties,
  listUnits,
  updateRoom,
  updateUnit,
} from "../../api/unitsAPI";
import { formatBedroomCount, formatUnitType, validateUnitForm } from "../../utils/unitForm";
import { CURRENCY_CODES, currencyPrecision, formatMoney } from "../../utils/money";
import "../manage.css";

const EMPTY_FORM = {
  property_id: "",
  unit_number: "",
  unit_type: "",
  bedrooms: "",
  bathrooms: "",
  rent_amount: "",
  floor_number: "1",
  layout: "",
  size: "",
  size_unit: "",
  furnished: false,
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
  "floor_number",
  "layout",
  "size",
  "size_unit",
  "furnished",
  "description",
];
// A unit cannot move to another property, so property_id is create-only.
const EDIT_FIELDS = [
  "unit_number",
  "unit_type",
  "bedrooms",
  "bathrooms",
  "rent_amount",
  "floor_number",
  "layout",
  "size",
  "size_unit",
  "furnished",
  "description",
];

const FIELD_CONFIG = {
  property_id: { label: "Property" },
  unit_number: { label: "Unit number", type: "text" },
  unit_type: { label: "Unit type", type: "select" },
  bedrooms: { label: "Bedrooms (0 for studio/bedsitter)", type: "number", min: "0", step: "1" },
  bathrooms: { label: "Bathrooms", type: "number", min: "0", max: "99.9", step: "0.5" },
  rent_amount: { label: "Monthly rent", type: "number", min: "0.01" },
  floor_number: { label: "Floor", type: "number", min: "1", step: "1" },
  layout: { label: "Layout (e.g. 2+1)", type: "text" },
  size: { label: "Size (optional)", type: "number", min: "0.01", step: "0.01" },
  size_unit: { label: "Size unit", type: "select" },
  furnished: { label: "Furnished", type: "checkbox" },
  description: { label: "Unit description (optional)", type: "textarea" },
};

function unitToForm(unit) {
  return {
    ...EMPTY_FORM,
    property_id: String(unit.property_id),
    currency: unit.currency,
    unit_number: unit.unit_number,
    unit_type: unit.unit_type ?? "",
    bedrooms: unit.bedrooms ?? "",
    bathrooms: unit.bathrooms ?? "",
    rent_amount: unit.rent_amount ?? "",
    floor_number: unit.floor_number ?? 1,
    layout: unit.layout ?? "",
    size: unit.size ?? "",
    size_unit: unit.size_unit ?? "",
    furnished: Boolean(unit.furnished),
    description: unit.description ?? "",
    availability_status: unit.availability_status ?? (unit.is_occupied ? "occupied" : "vacant"),
  };
}

// Empty optional fields become null so editing can clear them.
function toBody(form, fields) {
  const body = {};
  fields.forEach((name) => {
    const value = String(form[name] ?? "").trim();
    if (name === "furnished") body[name] = Boolean(form[name]);
    else if (name === "unit_number" || name === "unit_type" || name === "layout"
      || name === "size_unit" || name === "description") {
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
  if (unit.rent_amount != null) parts.push(`${formatMoney(unit.rent_amount, unit.currency)} per month`);
  if (unit.floor_number != null) parts.push(`Floor ${unit.floor_number}`);
  if (unit.layout) parts.push(`Layout ${unit.layout}`);
  if (unit.size != null) parts.push(`${unit.size} ${unit.size_unit}`);
  if (unit.furnished) parts.push("Furnished");
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
  const currency =
    properties.find((property) => String(property.id) === String(form.property_id))?.currency
    || initial.currency
    || CURRENCY_CODES[0];
  const selectedProperty = properties.find(
    (property) => String(property.id) === String(form.property_id)
  );

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: name === "furnished" ? event.target.checked : value,
    }));
    if (name === "property_id") onPropertyChange?.(value);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validateUnitForm(form, {
      requireProperty: fields.includes("property_id"),
      requireDetails: true,
      currency,
      floors: selectedProperty?.floors,
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
                {properties.filter((property) => property.rental_type !== "whole_property").map((property) => (
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
                {name === "unit_type" ? (
                  <>
                    <option value="">Choose a unit type</option>
                    <option value="bedsitter">Bedsitter</option>
                    <option value="studio">Studio</option>
                    <option value="one-bedroom">One bedroom</option>
                    <option value="two-bedroom">Two bedrooms</option>
                    <option value="three-bedroom">Three bedrooms</option>
                    <option value="four-bedroom">Four bedrooms</option>
                    <option value="other">Other</option>
                  </>
                ) : (
                  <>
                    <option value="">Choose unit</option>
                    <option value="sqm">Square metres</option>
                    <option value="sqft">Square feet</option>
                  </>
                )}
              </select>
            ) : config.type === "checkbox" ? (
              <input
                name={name}
                type="checkbox"
                checked={Boolean(form[name])}
                onChange={handleChange}
                aria-invalid={Boolean(errors[name])}
              />
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
                step={name === "rent_amount" ? 10 ** -currencyPrecision(currency) : config.step}
                value={form[name]}
                onChange={handleChange}
                aria-invalid={Boolean(errors[name])}
              />
            )}
            {name === "rent_amount" && <span>({currency})</span>}
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

const EMPTY_ROOM = {
  name: "",
  room_type: "bedroom",
  size: "",
  size_unit: "",
  description: "",
};

function RoomBreakdown({ unit, onChange }) {
  const [form, setForm] = useState(EMPTY_ROOM);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function startEdit(room) {
    setEditingId(room.id);
    setForm({
      name: room.name,
      room_type: room.room_type,
      size: room.size ?? "",
      size_unit: room.size_unit ?? "",
      description: room.description ?? "",
    });
    setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const body = {
      ...form,
      size: form.size === "" ? null : Number(form.size),
      size_unit: form.size_unit || null,
      description: form.description.trim() || null,
    };
    try {
      const saved = editingId
        ? await updateRoom(editingId, body)
        : await createRoom(unit.id, body);
      const rooms = editingId
        ? unit.rooms.map((room) => room.id === saved.id ? saved : room)
        : [...unit.rooms, saved];
      onChange({ ...unit, rooms });
      setForm(EMPTY_ROOM);
      setEditingId(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(room) {
    try {
      await deleteRoom(room.id);
      onChange({ ...unit, rooms: unit.rooms.filter((item) => item.id !== room.id) });
      if (editingId === room.id) {
        setEditingId(null);
        setForm(EMPTY_ROOM);
      }
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <section className="manage-card" aria-label={`Rooms for unit ${unit.unit_number}`}>
      <h3>Room breakdown</h3>
      {unit.rooms.length === 0 ? <p>No room details added.</p> : (
        <ul>
          {unit.rooms.map((room) => (
            <li key={room.id}>
              <strong>{room.name}</strong> · {room.room_type.replaceAll("_", " ")}
              {room.size != null ? ` · ${room.size} ${room.size_unit}` : ""}
              {room.description ? <p>{room.description}</p> : null}
              <button type="button" onClick={() => startEdit(room)}>Edit</button>
              <button type="button" onClick={() => handleDelete(room)}>Remove</button>
            </li>
          ))}
        </ul>
      )}
      <form className="manage-form" onSubmit={handleSubmit}>
        <h4>{editingId ? "Edit room" : "Add a room"}</h4>
        <label>
          Name
          <input
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            maxLength={80}
            required
          />
        </label>
        <label>
          Room type
          <select
            value={form.room_type}
            onChange={(event) => setForm((current) => ({ ...current, room_type: event.target.value }))}
          >
            <option value="bedroom">Bedroom</option>
            <option value="living_room">Living room</option>
            <option value="kitchen">Kitchen</option>
            <option value="bathroom">Bathroom</option>
            <option value="balcony">Balcony</option>
            <option value="other">Other</option>
          </select>
        </label>
        <div className="manage-form-row">
          <label>
            Size
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={form.size}
              onChange={(event) => setForm((current) => ({ ...current, size: event.target.value }))}
            />
          </label>
          <label>
            Size unit
            <select
              value={form.size_unit}
              onChange={(event) => setForm((current) => ({ ...current, size_unit: event.target.value }))}
            >
              <option value="">Choose unit</option>
              <option value="sqm">Square metres</option>
              <option value="sqft">Square feet</option>
            </select>
          </label>
        </div>
        <label>
          Description
          <textarea
            value={form.description}
            maxLength={1000}
            onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
          />
        </label>
        {error && <p className="manage-error" role="alert">{error}</p>}
        <div className="manage-actions">
          <button type="submit" className="manage-button" disabled={saving}>
            {saving ? "Saving…" : editingId ? "Save room" : "Add room"}
          </button>
          {editingId && (
            <button
              type="button"
              className="manage-button is-secondary"
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_ROOM);
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </section>
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
  const [unitFormOpen, setUnitFormOpen] = useState(false);
  const [unitNotice, setUnitNotice] = useState("");
  const [roomsUnitId, setRoomsUnitId] = useState(null);
  const [showBulkForm, setShowBulkForm] = useState(false);
  const [bulkForm, setBulkForm] = useState({
    units_per_floor: "5",
    layout: "2+1",
    rent_amount: "",
  });
  const [bulkError, setBulkError] = useState("");
  const [bulkMessage, setBulkMessage] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);

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
  const selectedProperty = properties.find(
    (property) => String(property.id) === selectedPropertyId
  );
  const unitsByFloor = selectedPropertyId
    ? units.reduce((groups, unit) => {
      (groups[unit.floor_number] ??= []).push(unit);
      return groups;
    }, {})
    : null;
  const bulkUnitsPerFloor = Number(bulkForm.units_per_floor);
  const bulkTotal = selectedProperty
    ? bulkUnitsPerFloor * selectedProperty.floors
    : 0;
  const bulkPreview = Number.isInteger(bulkUnitsPerFloor)
    && bulkUnitsPerFloor > 0
    && bulkUnitsPerFloor <= 99
    && bulkTotal <= 500
    ? Array.from({ length: Math.min(bulkTotal, 50) }, (_, index) => {
      const floor = Math.floor(index / bulkUnitsPerFloor) + 1;
      const sequence = (index % bulkUnitsPerFloor) + 1;
      return `${floor}${String(sequence).padStart(2, "0")}`;
    })
    : [];

  async function handleCreate(body) {
    const created = await createUnit(body);
    setUnits((current) => [...current, created]);
    setUnitFormOpen(false);
    setUnitNotice(`Unit ${created.unit_number} was added to the portfolio.`);
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

  async function handleBulkCreate(event) {
    event.preventDefault();
    setBulkError("");
    setBulkMessage("");
    if (!selectedProperty || !bulkPreview.length) {
      setBulkError("Choose a unit count that creates no more than 500 units.");
      return;
    }
    if (!bulkForm.layout.trim()) {
      setBulkError("Enter a layout for the new units.");
      return;
    }
    if (!bulkForm.rent_amount.trim()) {
      setBulkError("Enter a monthly rent for the new units.");
      return;
    }
    const validation = validateUnitForm(
      {
        ...EMPTY_FORM,
        layout: bulkForm.layout,
        rent_amount: bulkForm.rent_amount,
      },
      { currency: selectedProperty.currency }
    );
    if (Object.keys(validation).length > 0) {
      setBulkError(Object.values(validation)[0]);
      return;
    }

    setBulkSaving(true);
    try {
      const created = await bulkCreateUnits(selectedProperty.id, {
        units_per_floor: bulkUnitsPerFloor,
        layout: bulkForm.layout.trim(),
        rent_amount: Number(bulkForm.rent_amount),
      });
      setUnits((current) => [...current, ...created]);
      setBulkMessage(`Created ${created.length} units.`);
      setShowBulkForm(false);
    } catch (requestError) {
      setBulkError(requestError.message);
    } finally {
      setBulkSaving(false);
    }
  }

  return (
    <section className="manage-page">
      <header className="manage-page-heading">
        <div>
          <h1>Units</h1>
          <p className="manage-status">Manage availability, rental details, and room layouts across your properties.</p>
        </div>
        {properties.some((property) => property.rental_type !== "whole_property") && (
          <button type="button" className="manage-button" onClick={() => {
            setUnitNotice("");
            setUnitFormOpen(true);
          }}>
            Add unit
          </button>
        )}
      </header>

      {!isLoading && properties.length === 0 && (
        <p className="manage-status">Add a property first, then come back to add its units.</p>
      )}
      {selectedProperty?.rental_type === "whole_property" && (
        <p className="manage-status">
          Whole properties have one automatically created unit and cannot have additional units.
        </p>
      )}

      {unitFormOpen && (
        <div className="manage-dialog-backdrop">
          <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="unit-dialog-title">
            <div className="manage-dialog-heading">
              <div>
                <h2 id="unit-dialog-title">Add a unit</h2>
                <p>Set up a rentable unit and its availability details.</p>
              </div>
              <button type="button" className="manage-dialog-close" aria-label="Close unit form" onClick={() => setUnitFormOpen(false)}>×</button>
            </div>
            <UnitForm
              initial={{ ...EMPTY_FORM, property_id: selectedPropertyId }}
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
          </section>
        </div>
      )}

      {editingId !== null && units.some((unit) => unit.id === editingId) && (
        <div className="manage-dialog-backdrop">
          <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="edit-unit-dialog-title">
            <div className="manage-dialog-heading">
              <div>
                <h2 id="edit-unit-dialog-title">Edit unit</h2>
                <p>Update the unit details in your portfolio.</p>
              </div>
              <button type="button" className="manage-dialog-close" aria-label="Close unit editor" onClick={() => setEditingId(null)}>×</button>
            </div>
            <UnitForm
              initial={unitToForm(units.find((unit) => unit.id === editingId))}
              fields={EDIT_FIELDS}
              submitLabel="Save changes"
              onSubmit={(body) => handleUpdate(editingId, body)}
              onCancel={() => setEditingId(null)}
            />
          </section>
        </div>
      )}

      {selectedProperty && selectedProperty.rental_type !== "whole_property" && (
        <section className="manage-card bulk-units-card">
          <div>
            <h2>Bulk-create units</h2>
            <p>Creates the same layout and rent on every floor, using floor-based numbers.</p>
          </div>
          <button
            type="button"
            className="manage-button is-secondary"
            onClick={() => {
              setShowBulkForm(true);
              setBulkError("");
              setBulkMessage("");
            }}
          >
            Create units in bulk
          </button>
          {bulkMessage && <p role="status">{bulkMessage}</p>}
          {showBulkForm && (
            <div className="manage-dialog-backdrop">
            <section className="manage-dialog" role="dialog" aria-modal="true" aria-labelledby="bulk-unit-dialog-title">
            <div className="manage-dialog-heading">
              <div>
                <h2 id="bulk-unit-dialog-title">Bulk-create units</h2>
                <p>Create a consistent set of units for each floor.</p>
              </div>
              <button type="button" className="manage-dialog-close" aria-label="Close bulk unit form" disabled={bulkSaving} onClick={() => setShowBulkForm(false)}>×</button>
            </div>
            <form className="manage-form" onSubmit={handleBulkCreate}>
              <label>
                Units per floor
                <input
                  type="number"
                  min="1"
                  max="99"
                  step="1"
                  value={bulkForm.units_per_floor}
                  onChange={(event) =>
                    setBulkForm((current) => ({
                      ...current,
                      units_per_floor: event.target.value,
                    }))
                  }
                  required
                />
              </label>
              <label>
                Layout
                <select
                  value={bulkForm.layout}
                  onChange={(event) =>
                    setBulkForm((current) => ({ ...current, layout: event.target.value }))
                  }
                >
                  <option value="studio">Studio</option>
                  <option value="1+1">1+1</option>
                  <option value="2+1">2+1</option>
                  <option value="3+1">3+1</option>
                  <option value="4+1">4+1</option>
                  <option value="5+1">5+1</option>
                </select>
              </label>
              <label>
                Monthly rent ({selectedProperty.currency})
                <input
                  type="number"
                  min="0.01"
                  step={10 ** -currencyPrecision(selectedProperty.currency)}
                  value={bulkForm.rent_amount}
                  onChange={(event) =>
                    setBulkForm((current) => ({
                      ...current,
                      rent_amount: event.target.value,
                    }))
                  }
                  required
                />
              </label>
              <div className="bulk-unit-preview" aria-live="polite">
                <strong>Preview</strong>
                <p>
                  {bulkPreview.length
                    ? `${bulkTotal} units: ${bulkPreview.join(", ")}${bulkTotal > bulkPreview.length ? ", …" : ""}`
                    : "Choose a valid unit count to preview numbering."}
                </p>
                {bulkError && <p className="manage-error" role="alert">{bulkError}</p>}
                {bulkMessage && <p role="status">{bulkMessage}</p>}
              </div>
              <div className="manage-actions">
                <button type="submit" className="manage-button" disabled={bulkSaving}>
                  {bulkSaving ? "Creating…" : `Create ${bulkTotal || 0} units`}
                </button>
                <button type="button" className="manage-button is-secondary" disabled={bulkSaving} onClick={() => setShowBulkForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
            </section>
            </div>
          )}
        </section>
      )}

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
      {unitNotice && <p className="manage-status" role="status">{unitNotice}</p>}
      {isLoading && <p className="manage-status">Loading units…</p>}
      {!isLoading && units.length === 0 && !error && (
        <p className="manage-status">
          {selectedPropertyId ? "This property has no units yet. Add its first unit above." : "No units yet. Add your first one above."}
        </p>
      )}

      <div>
        {unitsByFloor
          ? Object.entries(unitsByFloor)
            .sort(([floorA], [floorB]) => Number(floorA) - Number(floorB))
            .map(([floor, floorUnits]) => (
              <section key={floor}>
                <h2>Floor {floor}</h2>
                <ul className="manage-list">{floorUnits.map((unit) => renderUnit(unit))}</ul>
              </section>
            ))
          : <ul className="manage-list">{units.map((unit) => renderUnit(unit))}</ul>}
      </div>
    </section>
  );

  function renderUnit(unit) {
    return (
          <li key={unit.id} className="manage-card">
              <>
                <div>
                  <strong>Unit {unit.unit_number}</strong>
                  <span className={`manage-badge is-${unit.availability_status}`}>
                    {unit.availability_status === "reserved"
                      ? "Reserved"
                      : unit.availability_status === "occupied"
                        ? "Occupied"
                        : "Vacant"}
                  </span>
                  <p>{propertyName(unit.property_id)} · Floor {unit.floor_number}</p>
                  <p>{unitDetails(unit)}</p>
                  <button
                    type="button"
                    className="manage-button is-secondary"
                    onClick={() => setRoomsUnitId((current) => current === unit.id ? null : unit.id)}
                  >
                    {roomsUnitId === unit.id ? "Hide rooms" : `Rooms (${unit.rooms.length})`}
                  </button>
                  {roomsUnitId === unit.id && (
                    <RoomBreakdown
                      unit={unit}
                      onChange={(updated) =>
                        setUnits((current) => current.map((item) => item.id === updated.id ? updated : item))
                      }
                    />
                  )}
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
          </li>
    );
  }
}

export default UnitsPage;
