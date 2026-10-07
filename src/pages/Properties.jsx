import { useEffect, useState } from "react";
import { searchProperties } from "../rentcastApi";
import { CITIES } from "../cities";
import PropertyCard from "../components/PropertyCard";

function Properties() {
  // Controlled <select>: holds the label of the chosen city
  const [selectedLabel, setSelectedLabel] = useState(CITIES[0].label);
  const [retryCount, setRetryCount] = useState(0);

  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const selectedCity = CITIES.find((c) => c.label === selectedLabel);

  useEffect(() => {
    let ignore = false; // stops an old request from overwriting a newer one

    searchProperties(selectedCity.city, selectedCity.state)
      .then((data) => {
        if (!ignore) setProperties(data);
      })
      .catch((err) => {
        if (!ignore) {
          setProperties([]);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [selectedCity.city, selectedCity.state, retryCount]);

  function handleCityChange(event) {
    setLoading(true);
    setError(null);
    setSelectedLabel(event.target.value);
  }

  function handleRetry() {
    setLoading(true);
    setError(null);
    setRetryCount((count) => count + 1);
  }

  return (
    <div className="properties-page">
      <h1>Properties</h1>
      <p>Browse available rental properties.</p>

      <div className="properties-filter">
        <label htmlFor="city-select">City</label>
        <select
          id="city-select"
          value={selectedLabel}
          onChange={handleCityChange}
        >
          {CITIES.map((c) => (
            <option key={c.label} value={c.label}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      {loading && <p className="status">Loading properties...</p>}

      {error && (
        <div className="status status--error">
          <p>{error}</p>
          <button onClick={handleRetry}>Try again</button>
        </div>
      )}

      {!loading && !error && properties.length === 0 && (
        <p className="status">No properties found for {selectedLabel}.</p>
      )}

      {!loading && !error && properties.length > 0 && (
        <>
          <p className="results-count">
            {properties.length} properties in {selectedLabel}
          </p>
          <div className="properties-grid">
            {properties.map((property) => (
              <PropertyCard key={property.id} property={property} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default Properties;