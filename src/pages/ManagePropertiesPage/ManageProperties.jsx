import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getToken } from "../../api/authAPI";
import {
  createProperty,
  deleteProperty,
  getPropertiesSummary,
  listProperties,
  updateProperty,
} from "../../api/propertiesApi";
import { uploadPropertyPhoto } from "../../api/mediaApi";
import { createUnit, listUnits } from "../../api/unitsAPI";
import {
  CURRENCY_CODES,
  PROPERTY_COUNTRIES,
  currencyForCountry,
  currencyPrecision,
} from "../../utils/money";
import { validateUnitForm } from "../../utils/unitForm";
import "./ManageProperties.css";

const EMPTY_FORM = {
  name: "",
  address_line: "",
  city: "",
  country: "KE",
  other_country_code: "",
  region: "",
  postal_code: "",
  time_zone: "Africa/Nairobi",
  currency: currencyForCountry("KE"),
  rental_type: "multi_unit",
  subtype: "apartment_block",
  floors: "1",
  description: "",
};
const EMPTY_UNIT_FORM = {
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
};
const MAX_PROPERTY_PHOTOS = 30;
const MAX_PROPERTY_PHOTO_BYTES = 10 * 1024 * 1024;
const PROPERTY_PHOTO_EXTENSIONS = new Set(["jpg", "jpeg", "png", "webp"]);

function toFormValues(property) {
  const country = property.country || "KE";
  return {
    name: property.name || "",
    address_line: property.address_line || property.address || "",
    city: property.city || "",
    country: PROPERTY_COUNTRIES.some((item) => item.code === country) ? country : "OTHER",
    other_country_code: PROPERTY_COUNTRIES.some((item) => item.code === country) ? "" : country,
    region: property.region || property.state || "",
    postal_code: property.postal_code || property.zip_code || "",
    time_zone: property.time_zone || "Africa/Nairobi",
    currency: property.currency || currencyForCountry(property.country || "KE"),
    rental_type: property.rental_type || "multi_unit",
    subtype: property.subtype || "apartment_block",
    floors: String(property.floors || 1),
    description: property.description || "",
  };
}

function propertyPayload(form) {
  const { other_country_code, ...values } = form;
  return {
    ...values,
    country: form.country === "OTHER" ? other_country_code.trim().toUpperCase() : form.country,
    floors: Number(form.floors),
  };
}

function wholeUnitPayload(unitForm, subtype) {
  return {
    unit_type: subtype,
    bedrooms: Number(unitForm.bedrooms),
    bathrooms: Number(unitForm.bathrooms),
    rent_amount: Number(unitForm.rent_amount),
    floor_number: Number(unitForm.floor_number || 1),
    layout: unitForm.layout || null,
    size: unitForm.size ? Number(unitForm.size) : null,
    size_unit: unitForm.size_unit || null,
    furnished: Boolean(unitForm.furnished),
    description: unitForm.description.trim() || null,
  };
}

function unitToForm(unit) {
  return {
    ...EMPTY_UNIT_FORM,
    unit_type: unit.unit_type || "",
    bedrooms: unit.bedrooms ?? "",
    bathrooms: unit.bathrooms ?? "",
    rent_amount: unit.rent_amount ?? "",
    floor_number: unit.floor_number ?? 1,
    layout: unit.layout ?? "",
    size: unit.size ?? "",
    size_unit: unit.size_unit ?? "",
    furnished: Boolean(unit.furnished),
    description: unit.description ?? "",
  };
}

function ManagePropertiesPage() {
  const loggedIn = Boolean(getToken());

  const [properties, setProperties] = useState([]);
  const [portfolioSummary, setPortfolioSummary] = useState(null);
  const [pagination, setPagination] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(loggedIn);
  const [loadError, setLoadError] = useState(null);
  const [reloadCount, setReloadCount] = useState(0);

  const [form, setForm] = useState(EMPTY_FORM);
  const [unitForm, setUnitForm] = useState(EMPTY_UNIT_FORM);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null);
  const [propertyPhotos, setPropertyPhotos] = useState([]);
  const [uploadedPropertyPhotoCount, setUploadedPropertyPhotoCount] = useState(0);
  const [pendingUnitPropertyId, setPendingUnitPropertyId] = useState(null);
  const [wholeUnitId, setWholeUnitId] = useState(null);

  useEffect(() => {
    if (!loggedIn) return undefined;

    let ignore = false; // stops an old request from overwriting a newer one

    Promise.all([listProperties({ page }), getPropertiesSummary()])
      .then(([data, summary]) => {
        if (!ignore) {
          setProperties(data.properties);
          setPagination(data.pagination);
          setPortfolioSummary(summary);
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
    setForm((current) => ({
      ...current,
      [name]: value,
      ...(name === "country" && currencyForCountry(value)
        ? { currency: currencyForCountry(value) }
        : {}),
    }));
  }
  function handleUnitChange(event) {
  const { name, value } = event.target;
  setUnitForm((current) => ({ ...current, [name]: value }));
}

function resetForm() {
  setFormOpen(false);
  setForm(EMPTY_FORM);
  setUnitForm(EMPTY_UNIT_FORM);
  setPropertyPhotos([]);
  setUploadedPropertyPhotoCount(0);
  setEditingId(null);
  setWholeUnitId(null);
  setPendingUnitPropertyId(null);
  setFormError(null);
}

function handlePropertyPhotoChange(event) {
  const files = Array.from(event.target.files ?? []);
  event.target.value = "";
  if (!files.length) return;

  const invalidFile = files.find((file) => {
    const extension = file.name.split(".").pop()?.toLowerCase();
    return !extension || !PROPERTY_PHOTO_EXTENSIONS.has(extension) || file.size > MAX_PROPERTY_PHOTO_BYTES;
  });
  if (invalidFile) {
    setFormError(
      invalidFile.size > MAX_PROPERTY_PHOTO_BYTES
        ? `${invalidFile.name} is larger than the 10 MB photo limit.`
        : `${invalidFile.name} is not a supported photo. Use JPG, PNG, or WebP.`,
    );
    return;
  }

  if (uploadedPropertyPhotoCount + propertyPhotos.length + files.length > MAX_PROPERTY_PHOTOS) {
    setFormError(`A property can have at most ${MAX_PROPERTY_PHOTOS} photos.`);
    return;
  }

  setFormError(null);
  setPropertyPhotos((current) => [...current, ...files]);
}

async function handleEdit(property) {
  setFormOpen(true);
  setEditingId(property.id);
  setForm(toFormValues(property));
  setUnitForm(EMPTY_UNIT_FORM);
  setPropertyPhotos([]);
  setUploadedPropertyPhotoCount(0);
  setWholeUnitId(null);
  setPendingUnitPropertyId(null);
  setFormError(null);
  if (property.rental_type === "whole_property") {
    try {
      const units = await listUnits(property.id);
      if (units.length !== 1 || units[0].unit_number !== "Entire property") {
        throw new Error("This whole property must have exactly one unit named Entire property.");
      }
      setWholeUnitId(units[0].id);
      setUnitForm(unitToForm(units[0]));
    } catch (error) {
      setFormError(error.message);
    }
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

  async function handleSubmit(event) {
  event.preventDefault();
  setFormError(null);

  // Editing an existing property does not create a unit.
  if (editingId) {
    if (form.rental_type === "whole_property") {
      if (!wholeUnitId) {
        setFormError("The whole property's unit details could not be loaded.");
        return;
      }
      const unitErrors = validateUnitForm(unitForm, {
        requireProperty: false,
        requireDetails: true,
        requireUnitNumber: false,
        requireUnitType: false,
        currency: form.currency,
        floors: Number(form.floors),
      });
      if (Object.keys(unitErrors).length > 0) {
        setFormError(Object.values(unitErrors)[0]);
        return;
      }
    }
    setSaving(true);

    try {
      const values = propertyPayload(form);
      if (form.rental_type === "whole_property" && wholeUnitId) {
        values.whole_unit = wholeUnitPayload(unitForm, form.subtype);
      }
      const updated = await updateProperty(editingId, values);

      setProperties((current) =>
        current.map((property) =>
          property.id === updated.id ? updated : property
        )
      );

      resetForm();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }

    return;
  }

  const isWholeProperty = form.rental_type === "whole_property";
  if (propertyPhotos.length === 0 && uploadedPropertyPhotoCount === 0) {
    setFormError("Add at least one property photo before saving.");
    return;
  }
  const unitErrors = validateUnitForm(unitForm, {
    requireProperty: false,
    requireDetails: true,
    requireUnitNumber: !isWholeProperty,
    requireUnitType: !isWholeProperty,
    currency: form.currency,
    floors: Number(form.floors),
  });

  if (Object.keys(unitErrors).length > 0) {
    setFormError(Object.values(unitErrors)[0]);
    return;
  }

  setSaving(true);

  try {
    let propertyId = pendingUnitPropertyId;

    // Create the property only if it has not already been saved.
    if (!propertyId) {
      const propertyValues = propertyPayload(form);
      if (isWholeProperty) {
        propertyValues.whole_unit = wholeUnitPayload(unitForm, form.subtype);
      }
      const created = await createProperty(propertyValues);

      propertyId = created.id;
      setPendingUnitPropertyId(propertyId);

      if (page === 1) {
        setProperties((current) =>
          [created, ...current.filter((p) => p.id !== created.id)].slice(0, 10)
        );
      } else {
        setPage(1);
      }
      setReloadCount((count) => count + 1);
    }

    for (const photo of propertyPhotos) {
      await uploadPropertyPhoto(propertyId, photo);
      setPropertyPhotos((current) => current.filter((item) => item !== photo));
      setUploadedPropertyPhotoCount((count) => count + 1);
    }

    if (isWholeProperty) {
      resetForm();
      return;
    }

    // Create the first unit using the saved property's ID.
    await createUnit({
      property_id: Number(propertyId),
      unit_number: unitForm.unit_number.trim(),
      unit_type: unitForm.unit_type,
      bedrooms: Number(unitForm.bedrooms),
      bathrooms: Number(unitForm.bathrooms),
      rent_amount: Number(unitForm.rent_amount),
      floor_number: Number(unitForm.floor_number || 1),
      layout: unitForm.layout || null,
      size: unitForm.size ? Number(unitForm.size) : null,
      size_unit: unitForm.size_unit || null,
      furnished: Boolean(unitForm.furnished),
      description: unitForm.description.trim() || null,
    });

    // Clear the form only after both operations succeed.
    resetForm();
    setReloadCount((count) => count + 1);
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

  function closeForm() {
    if (saving || pendingUnitPropertyId) return;
    resetForm();
  }

  const isWholeProperty = form.rental_type === "whole_property";

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
      <header className="properties-page-heading">
        <div>
          <p className="properties-eyebrow">LANDLORD WORKSPACE</p>
          <h1>My properties</h1>
          <p className="manage-intro">
            Keep your portfolio organized, track occupancy, and manage each
            property from one place.
          </p>
        </div>
        <button
          type="button"
          className="manage-button properties-add-button"
          onClick={() => {
            resetForm();
            setFormOpen(true);
          }}
        >
          <span aria-hidden="true">+</span> Add property
        </button>
      </header>
      {portfolioSummary && (
        <section className="portfolio-summary" aria-label="Portfolio occupancy summary">
          <div className="portfolio-summary-heading">
            <h2>Portfolio overview</h2>
            <span>Live occupancy</span>
          </div>
          <div className="portfolio-metrics">
            <div><strong>{portfolioSummary.property_count}</strong><span>Properties</span></div>
            <div><strong>{portfolioSummary.occupancy_summary.total_units}</strong><span>Total units</span></div>
            <div><strong>{portfolioSummary.occupancy_summary.occupied_units}</strong><span>Occupied</span></div>
            <div><strong>{portfolioSummary.occupancy_summary.reserved_units}</strong><span>Reserved</span></div>
            <div><strong>{portfolioSummary.occupancy_summary.vacant_units}</strong><span>Vacant</span></div>
          </div>
        </section>
      )}

      {formOpen && (
        <div className="property-dialog-backdrop">
          <section
            className="property-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="property-dialog-title"
          >
            <div className="property-dialog-heading">
              <div>
                <p className="properties-eyebrow">{editingId ? "PORTFOLIO UPDATE" : "NEW LISTING"}</p>
                <h2 id="property-dialog-title">{editingId ? "Edit property" : "Add a property"}</h2>
                <p>Enter the property details and first rentable unit to get your listing ready.</p>
              </div>
              <button
                className="property-dialog-close"
                type="button"
                onClick={closeForm}
                disabled={saving || Boolean(pendingUnitPropertyId)}
                aria-label="Close property form"
              >
                ×
              </button>
            </div>
            <form className="manage-form" onSubmit={handleSubmit}>

        {!editingId && (
          <label>
            Step 1 · Rental type *
            <select
              name="rental_type"
              value={form.rental_type}
              onChange={handleChange}
              required
            >
              <option value="multi_unit">Building with multiple units</option>
              <option value="whole_property">Single property rented as a whole</option>
            </select>
          </label>
        )}

        <div className="manage-form-row">
          <label>
            Property type *
            <select name="subtype" value={form.subtype} onChange={handleChange} required>
              <option value="apartment_block">Apartment block</option>
              <option value="bungalow">Bungalow</option>
              <option value="maisonette">Maisonette</option>
              <option value="villa">Villa</option>
              <option value="townhouse">Townhouse</option>
              <option value="commercial">Commercial</option>
            </select>
          </label>
          {form.rental_type === "multi_unit" && (
            <label>
              Number of floors *
              <input
                type="number"
                name="floors"
                value={form.floors}
                onChange={handleChange}
                min="1"
                step="1"
                required
              />
            </label>
          )}
        </div>

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
          Address line *
          <input
            name="address_line"
            value={form.address_line}
            onChange={handleChange}
            maxLength={255}
            required
          />
        </label>

        <div className="manage-form-row">
          <label>
            Country *
            <select name="country" value={form.country} onChange={handleChange} required>
              {PROPERTY_COUNTRIES.map(({ code, name }) => (
                <option key={code} value={code}>{name}</option>
              ))}
              <option value="OTHER">Other (enter ISO code)</option>
            </select>
          </label>
          {form.country === "OTHER" && (
            <label>
              Two-letter country code *
              <input
                name="other_country_code"
                value={form.other_country_code}
                onChange={handleChange}
                pattern="[A-Za-z]{2}"
                maxLength={2}
                required
              />
            </label>
          )}
          <label>
            Region / state
            <input
              name="region"
              value={form.region}
              onChange={handleChange}
              maxLength={100}
            />
          </label>
        </div>

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
            Postal code
            <input
              name="postal_code"
              value={form.postal_code}
              onChange={handleChange}
              maxLength={20}
            />
          </label>
          <label>
            Time zone *
            <input
              name="time_zone"
              value={form.time_zone}
              onChange={handleChange}
              maxLength={64}
              placeholder="Area/Location"
              required
            />
          </label>
        </div>

        <label>
          Property currency *
          <select name="currency" value={form.currency} onChange={handleChange} required>
            {CURRENCY_CODES.map((currency) => (
              <option key={currency} value={currency}>{currency}</option>
            ))}
          </select>
        </label>

        <label>
          Description
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={3}
          />
        </label>
        {!editingId && (
          <div className="property-photo-picker">
            <label htmlFor="property-photos">Property photos *</label>
            <input
              id="property-photos"
              type="file"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              multiple
              onChange={handlePropertyPhotoChange}
              aria-describedby="property-photos-help"
            />
            <small id="property-photos-help">
              Add at least one JPG, PNG, or WebP photo (up to 10 MB each). The first photo will be the cover.
            </small>
            {propertyPhotos.length > 0 && (
              <ul className="property-photo-selection" aria-label="Selected property photos">
                {propertyPhotos.map((photo, index) => (
                  <li key={`${photo.name}-${photo.lastModified}-${index}`}>
                    <span>{photo.name} · {Math.ceil(photo.size / 1024)} KB</span>
                    <button
                      type="button"
                      className="manage-button manage-button--ghost"
                      onClick={() =>
                        setPropertyPhotos((current) => current.filter((item) => item !== photo))
                      }
                      aria-label={`Remove ${photo.name}`}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {(!editingId || isWholeProperty) && (
  <div className="property-unit-section">
            <h3>{isWholeProperty ? "Whole property details" : "First unit details"}</h3>
            <p>
              {isWholeProperty
                ? "This property is rented as one unit. Its unit will be created automatically."
                : "Enter the details of the first rentable unit."}
            </p>

            {!isWholeProperty && <label>
              Unit number *
              <input
        name="unit_number"
        value={unitForm.unit_number}
        onChange={handleUnitChange}
        maxLength={50}
        required
      />
    </label>}

    {!isWholeProperty && <label>
      Unit type *
      <select
        name="unit_type"
        value={unitForm.unit_type}
        onChange={handleUnitChange}
        required
      >
        <option value="">Choose unit type</option>
        <option value="bedsitter">Bedsitter</option>
        <option value="studio">Studio</option>
        <option value="one-bedroom">One bedroom</option>
        <option value="two-bedroom">Two bedrooms</option>
        <option value="three-bedroom">Three bedrooms</option>
        <option value="four-bedroom">Four bedrooms</option>
        <option value="other">Other</option>
      </select>
    </label>}

    <div className="manage-form-row">
      <label>
        Bedrooms *
        <input
          type="number"
          name="bedrooms"
          value={unitForm.bedrooms}
          onChange={handleUnitChange}
          min="0"
          step="1"
          required
        />
        <small>Enter 0 for a studio or bedsitter.</small>
      </label>

      <label>
        Bathrooms *
        <input
          type="number"
          name="bathrooms"
          value={unitForm.bathrooms}
          onChange={handleUnitChange}
          min="0"
          max="99.9"
          step="0.1"
          required
        />
      </label>

      <label>
        Monthly rent ({form.currency}) *
        <input
          type="number"
          name="rent_amount"
          value={unitForm.rent_amount}
          onChange={handleUnitChange}
          min="0.01"
          max="99999999.99"
          step={10 ** -currencyPrecision(form.currency)}
          required
        />
      </label>
      {!isWholeProperty && (
        <label>
          Floor *
          <input
            type="number"
            name="floor_number"
            value={unitForm.floor_number}
            onChange={handleUnitChange}
            min="1"
            max={form.floors}
            step="1"
            required
          />
        </label>
      )}
    </div>

    <div className="manage-form-row">
        <label>
          Layout (optional)
          <input
            name="layout"
            value={unitForm.layout}
            onChange={handleUnitChange}
            maxLength={20}
            placeholder="2+1 or studio"
          />
        </label>
        <label>
          Unit size (optional)
          <input
            type="number"
            name="size"
            value={unitForm.size}
            onChange={handleUnitChange}
            min="0.01"
            step="0.01"
          />
        </label>
        <label>
          Size unit
          <select
            name="size_unit"
            value={unitForm.size_unit}
            onChange={handleUnitChange}
          >
            <option value="">Choose unit</option>
            <option value="sqm">Square metres</option>
            <option value="sqft">Square feet</option>
          </select>
        </label>
      </div>

    <label>
      <input
        type="checkbox"
        name="furnished"
        checked={unitForm.furnished}
        onChange={(event) =>
          setUnitForm((current) => ({ ...current, furnished: event.target.checked }))
        }
      />
      Furnished
    </label>

    <label>
      Unit description
      <textarea
        name="description"
        value={unitForm.description}
        onChange={handleUnitChange}
        maxLength={5000}
        rows={3}
      />
    </label>
  </div>
)}

        {formError && (
          <p className="manage-error" role="alert">
            {formError}
          </p>
        )}

        <div className="manage-actions">
          <button type="submit" className="manage-button" disabled={saving}>
            {saving ? "Saving..." : editingId ? "Save changes" : "Add property"}
          </button>
          <button
            type="button"
            className="manage-button manage-button--ghost"
            onClick={closeForm}
            disabled={saving || Boolean(pendingUnitPropertyId)}
          >
            Cancel
          </button>
        </div>
            </form>
          </section>
        </div>
      )}

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
        <div className="properties-empty-state">
          <span aria-hidden="true">⌂</span>
          <h2>Your portfolio is ready to begin</h2>
          <p>Add your first property to start managing units, occupancy, and rental details.</p>
          <button type="button" className="manage-button" onClick={() => setFormOpen(true)}>
            Add your first property
          </button>
        </div>
      )}

      {properties.length > 0 && (
        <section className="properties-portfolio">
          <div className="properties-section-heading">
            <div>
              <p className="properties-eyebrow">YOUR COLLECTION</p>
              <h2>Property portfolio</h2>
            </div>
            {pagination && <span>{pagination.total} {pagination.total === 1 ? "property" : "properties"}</span>}
          </div>
          <ul className="manage-list">
            {properties.map((property) => (
            <li key={property.id} className="manage-item">
              <div className="manage-item-info">
                <h3>{property.name}</h3>
                <p>
                  {property.address_line || property.address}, {property.city}
                  {property.region || property.state ? `, ${property.region || property.state}` : ""}
                  {property.postal_code || property.zip_code ? ` ${property.postal_code || property.zip_code}` : ""}
                </p>
                <p>
                  {property.rental_type === "whole_property" ? "Whole property" : "Multi-unit property"}
                  {" · "}{property.subtype?.replaceAll("_", " ") || "apartment block"}
                  {property.rental_type !== "whole_property" ? ` · ${property.floors} floors` : ""}
                </p>
                {property.occupancy_summary && (
                  <p className="property-occupancy-summary">
                    {property.occupancy_summary.total_units} units ·{" "}
                    {property.occupancy_summary.occupied_units} occupied ·{" "}
                    {property.occupancy_summary.reserved_units} reserved ·{" "}
                    {property.occupancy_summary.vacant_units} vacant
                  </p>
                )}
                {property.description && (
                  <p className="manage-item-description">
                    {property.description}
                  </p>
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
                {property.rental_type !== "whole_property" && (
                  <Link
                    className="manage-button manage-button--ghost"
                    to={`/units?property_id=${property.id}`}
                  >
                    Manage units
                  </Link>
                )}
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
        </section>
      )}
    </section>
  );
}

export default ManagePropertiesPage;
