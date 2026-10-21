import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import SearchBar from "../../Components/SearchBar/SearchBar";
import { listPublicUnits } from "../../api/propertiesApi";
import { formatBedroomCount, formatUnitType } from "../../utils/unitForm";
import { formatMoney } from "../../utils/money";
import "./SearchPage.css";

const PER_PAGE = 9;

function SearchPage() {
  const [units, setUnits] = useState([]);
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [minRent, setMinRent] = useState("");
  const [maxRent, setMaxRent] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [bathrooms, setBathrooms] = useState("");
  const [unitType, setUnitType] = useState("");
  const [availability, setAvailability] = useState("vacant");
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let ignore = false;

    async function loadProperties() {
      setIsLoading(true);
      setError("");
      try {
        const result = await listPublicUnits({
          page,
          perPage: PER_PAGE,
          q: query,
          location: city,
          minRent,
          maxRent,
          bedrooms,
          bathrooms,
          unitType,
          availability,
        });
        if (!ignore) {
          setUnits(result.units);
          setPagination(result.pagination);
        }
      } catch (requestError) {
        if (!ignore) {
          setUnits([]);
          setPagination(null);
          setError(requestError.message || "Could not load properties.");
        }
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }

    loadProperties();
    return () => {
      ignore = true;
    };
  }, [page, query, city, minRent, maxRent, bedrooms, bathrooms, unitType, availability, retryCount]);

  function updateSearch(value) {
    setQuery(value);
    setPage(1);
  }

  function updateCity(event) {
    setCity(event.target.value);
    setPage(1);
  }

  return (
    <div className="search-page">
      <header className="search-page-header">
        <h1>Find a rental unit</h1>
        <p>Browse available apartments and homes, then filter by location, layout, and monthly rent.</p>
      </header>

      <div className="search-page-searchbar">
        <SearchBar onSearch={updateSearch} isLoading={isLoading} />
      </div>

      <div className="search-location">
        <label htmlFor="property-city">Location</label>
        <input
          id="property-city"
          type="search"
          value={city}
          onChange={updateCity}
          placeholder="City, address, or area"
          maxLength={100}
        />
      </div>

      <div className="search-filters" aria-label="Property filters">
        <label>
          Minimum rent
          <input
            type="number"
            min="0"
            step="0.01"
            value={minRent}
            onChange={(event) => {
              setMinRent(event.target.value);
              setPage(1);
            }}
          />
        </label>
        <label>
          Maximum rent
          <input
            type="number"
            min="0"
            step="0.01"
            value={maxRent}
            onChange={(event) => {
              setMaxRent(event.target.value);
              setPage(1);
            }}
          />
        </label>
        <label>
          Bedrooms
          <select
            value={bedrooms}
            onChange={(event) => {
              setBedrooms(event.target.value);
              setPage(1);
            }}
          >
            <option value="">Any</option>
            {[0, 1, 2, 3, 4, 5].map((count) => (
              <option key={count} value={count}>
                {count === 0 ? "Studio / bedsitter" : `${count} ${count === 1 ? "bedroom" : "bedrooms"}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Bathrooms
          <select
            value={bathrooms}
            onChange={(event) => {
              setBathrooms(event.target.value);
              setPage(1);
            }}
          >
            <option value="">Any</option>
            {["1", "1.5", "2", "2.5", "3", "4"].map((count) => (
              <option key={count} value={count}>{count}</option>
            ))}
          </select>
        </label>
        <label>
          Unit type
          <select
            value={unitType}
            onChange={(event) => {
              setUnitType(event.target.value);
              setPage(1);
            }}
          >
            <option value="">Any type</option>
            <option value="bedsitter">Bedsitter</option>
            <option value="studio">Studio</option>
            <option value="one-bedroom">One bedroom</option>
            <option value="two-bedroom">Two bedrooms</option>
            <option value="three-bedroom">Three bedrooms</option>
            <option value="four-bedroom">Four bedrooms</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          Availability
          <select
            value={availability}
            onChange={(event) => {
              setAvailability(event.target.value);
              setPage(1);
            }}
          >
            <option value="vacant">Available units</option>
            <option value="reserved">Reserved units</option>
            <option value="all">All units</option>
            <option value="occupied">Occupied only</option>
          </select>
        </label>
      </div>

      <div className="results-area">
        {error && (
          <div className="error-message" role="alert">
            <p>{error}</p>
            <button
              type="button"
              onClick={() => setRetryCount((count) => count + 1)}
            >
              Try again
            </button>
          </div>
        )}

        {isLoading && <p className="status">Loading rental units...</p>}

        {!isLoading && !error && pagination && (
          <div className="results-header">
            <p className="results-count">
              Showing {units.length} of {pagination.total} units
            </p>
          </div>
        )}

        {!isLoading && !error && units.length === 0 && (
          <div className="empty-state">
            <h2>No matching units found</h2>
            <p>Try changing the location, unit type, bedroom count, or rent range.</p>
          </div>
        )}

        {!isLoading && !error && units.length > 0 && (
          <div className="property-grid">
            {units.map((unit) => (
              <Link
                to={`/properties/${unit.property_id}#unit-${unit.id}`}
                key={unit.id}
                className="property-card"
              >
                <div className="property-card-top">
                  <h2>{unit.property_name} · Unit {unit.unit_number}</h2>
                </div>
                <p className="property-card-address">
                  {unit.property_address_line || unit.property_address}, {unit.property_city}
                  {unit.property_region || unit.property_state ? `, ${unit.property_region || unit.property_state}` : ""}
                  {unit.property_postal_code || unit.property_zip_code ? ` ${unit.property_postal_code || unit.property_zip_code}` : ""}
                </p>
                <p className="property-card-layouts">
                  {formatUnitType(unit.unit_type, unit.bedrooms)} · {formatBedroomCount(unit.bedrooms)}
                  {unit.layout ? ` · Layout ${unit.layout}` : ""}
                  {unit.bathrooms != null ? ` · ${unit.bathrooms} bathrooms` : ""}
                  {unit.size != null ? ` · ${unit.size} ${unit.size_unit}` : ""}
                  {unit.furnished ? " · Furnished" : ""}
                  {unit.floor_number != null ? ` · Floor ${unit.floor_number}` : ""}
                </p>
                <p>
                  {unit.rent_amount != null
                    ? `${formatMoney(unit.rent_amount, unit.currency)} per month`
                    : "Rent not specified"}
                </p>
                <span className={`unit-availability is-${unit.availability_status}`}>
                  {unit.availability_status === "occupied"
                    ? "Occupied"
                    : unit.availability_status === "reserved"
                      ? "Reserved"
                      : "Available"}
                </span>
                {unit.description && <p>{unit.description}</p>}
              </Link>
            ))}
          </div>
        )}

        {!isLoading && !error && pagination?.pages > 1 && (
          <nav className="pagination-controls" aria-label="Property pages">
            <button
              type="button"
              onClick={() => setPage((current) => current - 1)}
              disabled={!pagination.has_prev}
            >
              Previous
            </button>
            <span>
              Page {pagination.page} of {pagination.pages}
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
    </div>
  );
}

export default SearchPage;
