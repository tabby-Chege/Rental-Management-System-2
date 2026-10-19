import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  getPublicProperty,
  listPublicPropertyUnits,
} from "../../api/propertiesApi";
import { createApplication } from "../../api/applicationsApi";
import { getCurrentUser, getToken } from "../../api/authAPI";
import { formatBedroomCount, formatUnitType } from "../../utils/unitForm";
import "./PropertyDetail.css";

function PropertyDetailsPage() {
  const { id } = useParams();
  const location = useLocation();
  const selectedUnitId = location.hash.startsWith("#unit-")
    ? location.hash.slice("#unit-".length)
    : "";
  const [property, setProperty] = useState(null);
  const [units, setUnits] = useState([]);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [applicationError, setApplicationError] = useState("");
  const [applicationMessage, setApplicationMessage] = useState("");
  const [moveInDate, setMoveInDate] = useState("");
  const [message, setMessage] = useState("");
  const [applyingUnitId, setApplyingUnitId] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let ignore = false;

    async function loadProperty() {
      setIsLoading(true);
      setError("");
      try {
        const [result, unitResult] = await Promise.all([
          getPublicProperty(id),
          listPublicPropertyUnits(id, { unitId: selectedUnitId }),
        ]);
        if (!ignore) {
          setProperty(result);
          setUnits(unitResult.units);
        }
      } catch (requestError) {
        if (!ignore) {
          setProperty(null);
          setUnits([]);
          setError(requestError.message || "Could not load property.");
        }
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }

    loadProperty();
    if (getToken()) {
      getCurrentUser()
        .then(({ user: currentUser }) => {
          if (!ignore) setUser(currentUser);
        })
        .catch(() => {
          if (!ignore) setUser(null);
        });
    } else {
      setUser(null);
    }
    return () => {
      ignore = true;
    };
  }, [id, retryCount, selectedUnitId]);

  useEffect(() => {
    if (!isLoading && location.hash.startsWith("#unit-")) {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "center" });
    }
  }, [isLoading, location.hash, units]);

  async function applyForUnit(unit) {
    setApplicationError("");
    setApplicationMessage("");
    setApplyingUnitId(unit.id);
    try {
      const application = await createApplication({
        unit_id: unit.id,
        move_in_date: moveInDate,
        message,
      });
      setApplicationMessage(`Application submitted for unit ${unit.unit_number}.`);
      setUnits((current) => current.map((item) =>
        item.id === unit.id ? { ...item, has_pending_application: true } : item
      ));
      return application;
    } catch (requestError) {
      setApplicationError(requestError.message || "Could not submit your application.");
    } finally {
      setApplyingUnitId(null);
    }
  }

  if (isLoading) {
    return (
      <div className="details-page" aria-live="polite">
        <p>Loading property...</p>
      </div>
    );
  }

  if (error || !property) {
    return (
      <div className="details-page">
        <Link to="/properties" className="details-back">
          Back to properties
        </Link>
        <p className="details-error" role="alert">
          {error || "Property not found."}
        </p>
        {error && (
          <button type="button" onClick={() => setRetryCount((count) => count + 1)}>
            Try again
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="details-page">
      <Link to="/properties" className="details-back">
        Back to properties
      </Link>
      <header className="details-header">
        <h1>{property.name}</h1>
        <p className="details-address">
          {property.address}, {property.city}, {property.state}
          {property.zip_code ? ` ${property.zip_code}` : ""}
        </p>
      </header>
      {property.description && (
        <section className="details-box">
          <h2>Notes</h2>
          <p>{property.description}</p>
        </section>
      )}
      <section className="details-box details-units">
        <h2>Units at this property</h2>
        {units.length === 0 && <p>No units are listed for this property yet.</p>}
        <ul>
          {units.map((unit) => (
            <li key={unit.id} id={`unit-${unit.id}`} className="details-unit">
              <div>
                <strong>Unit {unit.unit_number}</strong>
                <p>
                  {formatUnitType(unit.unit_type, unit.bedrooms)}
                  {" · "}
                  {formatBedroomCount(unit.bedrooms)}
                  {unit.bathrooms != null ? ` · ${unit.bathrooms} bathrooms` : ""}
                  {unit.rent_amount != null
                    ? ` · KES ${Number(unit.rent_amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} per month`
                    : ""}
                </p>
                <span className={`manage-badge is-${unit.availability_status || (unit.is_occupied ? "occupied" : "vacant")}`}>
                  {unit.is_occupied ? "Occupied" : "Available"}
                </span>
                {unit.description && <p>{unit.description}</p>}
              </div>
              {user?.role === "tenant" && !unit.is_occupied && !unit.has_pending_application && (
                <button
                  type="button"
                  className="manage-button"
                  disabled={!moveInDate || applyingUnitId === unit.id}
                  onClick={() => applyForUnit(unit)}
                >
                  {applyingUnitId === unit.id ? "Submitting…" : "Apply"}
                </button>
              )}
              {unit.has_pending_application && <span>Application submitted</span>}
            </li>
          ))}
        </ul>
        {user?.role === "tenant" && units.some((unit) => !unit.is_occupied && !unit.has_pending_application) && (
          <div className="application-form">
            <label>
              Requested move-in date
              <input
                type="date"
                value={moveInDate}
                onChange={(event) => setMoveInDate(event.target.value)}
                required
              />
            </label>
            <label>
              Message to the property manager (optional)
              <textarea
                value={message}
                maxLength={5000}
                onChange={(event) => setMessage(event.target.value)}
              />
            </label>
          </div>
        )}
        {user?.role === "tenant" && applicationError && (
          <p className="details-error" role="alert">{applicationError}</p>
        )}
        {applicationMessage && <p role="status">{applicationMessage}</p>}
        {!user && <p><Link to="/login">Log in as a tenant to apply</Link></p>}
        {user && user.role !== "tenant" && (
          <p>Applications are available to tenant accounts.</p>
        )}
      </section>
      {(user?.role === "landlord" || user?.role === "admin") &&
        (user?.role === "admin" || user.id === property.owner_id) && (
        <Link to={`/units?property_id=${property.id}`}>Manage this property&apos;s units</Link>
      )}
    </div>
  );
}

export default PropertyDetailsPage;
