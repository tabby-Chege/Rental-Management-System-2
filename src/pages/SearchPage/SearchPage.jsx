import { useCallback, useEffect, useState } from "react";
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
  const [searchResetKey, setSearchResetKey] = useState(0);
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

  const updateSearch = useCallback((value) => {
    setQuery(value);
    setPage(1);
  }, []);

  const updateCity = useCallback((event) => {
    setCity(event.target.value);
    setPage(1);
  }, []);

  const activeFilterCount = [
    query,
    city,
    minRent,
    maxRent,
    bedrooms,
    bathrooms,
    unitType,
    availability !== "vacant",
  ].filter(Boolean).length;

  function clearFilters() {
    setQuery("");
    setCity("");
    setMinRent("");
    setMaxRent("");
    setBedrooms("");
    setBathrooms("");
    setUnitType("");
    setAvailability("vacant");
    setPage(1);
    setSearchResetKey((current) => current + 1);
  }

  return (
    <div className="search-page">
      <header className="search-page-header">
        <div className="search-page-heading">
          <span className="search-page-eyebrow">A place to call yours</span>
          <h1>Find your next home</h1>
          <p>Thoughtfully browse rental homes, compare the details, and find the right fit for your life.</p>
        </div>
        <div className="search-page-header-note" aria-hidden="true">
          <span>01</span>
          <span>Find a place<br />that feels like home</span>
        </div>
      </header>

      <section className="search-discovery-panel" aria-label="Search rental homes">
        <div className="search-page-searchbar">
          <SearchBar
            key={searchResetKey}
            onSearch={updateSearch}
            isLoading={isLoading}
          />
        </div>

        <div className="search-location">
          <label htmlFor="property-city">
            <span className="search-field-icon" aria-hidden="true">⌖</span>
            Location
          </label>
          <input
            id="property-city"
            type="search"
            value={city}
            onChange={updateCity}
            placeholder="City, address, or neighbourhood"
            maxLength={100}
          />
        </div>

        <div className="search-filters" aria-label="Property filters">
          <div className="search-filter-heading">
            <div>
              <h2>Make it yours</h2>
              <p>Fine-tune your search with the details that matter.</p>
            </div>
            {activeFilterCount > 0 && (
              <button type="button" className="search-clear-filters" onClick={clearFilters}>
                Clear filters <span>{activeFilterCount}</span>
              </button>
            )}
          </div>
          <div className="search-filter-fields">
            <label>
              Monthly rent
              <span className="search-rent-range">
                <span className="search-filter-prefix">From</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={minRent}
                  onChange={(event) => {
                    setMinRent(event.target.value);
                    setPage(1);
                  }}
                  placeholder="Any"
                  aria-label="Minimum monthly rent"
                />
                <span className="search-filter-prefix">To</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={maxRent}
                  onChange={(event) => {
                    setMaxRent(event.target.value);
                    setPage(1);
                  }}
                  placeholder="Any"
                  aria-label="Maximum monthly rent"
                />
              </span>
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
                <option value="">Any number</option>
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
                <option value="">Any number</option>
                {["1", "1.5", "2", "2.5", "3", "4"].map((count) => (
                  <option key={count} value={count}>{count}</option>
                ))}
              </select>
            </label>
            <label>
              Home type
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
                <option value="vacant">Available homes</option>
                <option value="reserved">Reserved homes</option>
                <option value="all">All homes</option>
                <option value="occupied">Occupied homes</option>
              </select>
            </label>
          </div>
        </div>
      </section>

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
            <div>
              <span className="results-eyebrow">Your search results</span>
              <h2 className="results-title">
                {pagination.total === 1 ? "1 home to explore" : `${pagination.total} homes to explore`}
              </h2>
              <p className="results-count">Showing {units.length} of {pagination.total} rental units</p>
            </div>
            {activeFilterCount > 0 && (
              <button type="button" className="search-clear-filters" onClick={clearFilters}>
                Reset search
              </button>
            )}
          </div>
        )}

        {!isLoading && !error && units.length === 0 && (
          <div className="empty-state">
            <span className="empty-state-art" aria-hidden="true">⌂</span>
            <span className="results-eyebrow">A little more searching</span>
            <h2>No homes match just yet</h2>
            <p>Try widening your filters or searching another neighbourhood. Your next place may be just around the corner.</p>
            {activeFilterCount > 0 && (
              <button type="button" onClick={clearFilters}>Clear all filters</button>
            )}
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
                <div className="property-card-image">
                  {unit.photo_url ? (
                    <img src={unit.photo_url} alt={`${unit.property_name}, Unit ${unit.unit_number}`} loading="lazy" />
                  ) : (
                    <div className="property-card-placeholder" aria-hidden="true">
                      <span>⌂</span>
                      <small>A place to belong</small>
                    </div>
                  )}
                  <span className={`unit-availability is-${unit.availability_status}`}>
                  {unit.availability_status === "occupied"
                    ? "Occupied"
                    : unit.availability_status === "reserved"
                      ? "Reserved"
                      : "Available"}
                  </span>
                </div>
                <div className="property-card-content">
                  <div className="property-card-top">
                    <div>
                      <span className="property-card-unit">{formatUnitType(unit.unit_type, unit.bedrooms)}</span>
                      <h2>{unit.property_name}</h2>
                    </div>
                    <span className="property-card-unit-number">Unit {unit.unit_number}</span>
                  </div>
                  <p className="property-card-address">
                    <span aria-hidden="true">⌖</span>
                    {unit.property_address_line || unit.property_address}, {unit.property_city}
                    {unit.property_region || unit.property_state ? `, ${unit.property_region || unit.property_state}` : ""}
                    {unit.property_postal_code || unit.property_zip_code ? ` ${unit.property_postal_code || unit.property_zip_code}` : ""}
                  </p>
                  <div className="property-card-details">
                    <span>{formatBedroomCount(unit.bedrooms)}</span>
                    {unit.bathrooms != null && <span>{unit.bathrooms} bath</span>}
                    {unit.size != null && <span>{unit.size} {unit.size_unit}</span>}
                    {unit.furnished && <span>Furnished</span>}
                  </div>
                  {unit.description && <p className="property-card-description">{unit.description}</p>}
                  <div className="property-card-footer">
                    <p className="property-card-price">
                      <strong>
                        {unit.rent_amount != null
                          ? formatMoney(unit.rent_amount, unit.currency)
                          : "Rent not specified"}
                      </strong>
                      {unit.rent_amount != null && <span> / month</span>}
                    </p>
                    <span className="property-card-view" aria-hidden="true">View home <span>↗</span></span>
                  </div>
                </div>
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
