import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import SearchBar from "../../Components/SearchBar/SearchBar";
import { searchProperties } from "../../api/rentcastAPI";
import { normalizeProperty } from "../../utils/propertyAdapter";
import { CITIES } from "../../data/cities";
import { filterProperties } from "../../utils/propertySearch";
import "./SearchPage.css";

const CURRENT_YEAR = new Date().getFullYear();

function SearchPage() {
  const [properties, setProperties] = useState([]);
  const [selectedCityLabel, setSelectedCityLabel] = useState(CITIES[0].label);
  const [retryCount, setRetryCount] = useState(0);
  const [query, setQuery] = useState("");
  const [ageFilter, setAgeFilter] = useState("all");
  const [sizeFilter, setSizeFilter] = useState("all");
  const [sortBy, setSortBy] = useState("default");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const selectedCity = CITIES.find((city) => city.label === selectedCityLabel) ?? CITIES[0];

  useEffect(() => {
    let ignore = false;

    async function loadProperties() {
      setIsLoading(true);
      setError("");

      try {
        const data = await searchProperties(selectedCity.city, selectedCity.state);
        if (!Array.isArray(data)) {
          throw new Error("The property service returned an unexpected response.");
        }
        if (!ignore) setProperties(data.map(normalizeProperty));
      } catch (err) {
        if (!ignore) {
          setProperties([]);
          setError(err.message || "Could not load properties. Please try again.");
        }
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }

    loadProperties();
    return () => {
      ignore = true;
    };
  }, [selectedCity, retryCount]);

  const results = filterProperties(properties, { query, ageFilter, sizeFilter, sortBy });

  function clearAll() {
    setQuery("");
    setAgeFilter("all");
    setSizeFilter("all");
    setSortBy("default");
  }

  const activeCount = [ageFilter, sizeFilter].filter(
    (value) => value !== "all"
  ).length + Number(Boolean(query)) + Number(sortBy !== "default");

  return (
    <div className="search-page">
      <header className="search-page-header">
        <h1>Find a rental property</h1>
        <p>
           Search by name, address, city, or zip. Filter properties by age and size.
            </p>
      </header>

      <div className="search-page-searchbar">
        <SearchBar onSearch={setQuery} isLoading={isLoading} />
      </div>

      <div className="search-location">
        <label htmlFor="property-city">Location</label>
        <select
          id="property-city"
          value={selectedCityLabel}
          onChange={(event) => setSelectedCityLabel(event.target.value)}
          disabled={isLoading}
        >
          {CITIES.map((city) => (
            <option key={city.label} value={city.label}>{city.label}</option>
          ))}
        </select>
      </div>

      <div className="search-page-layout">
        <aside className="filter-panel">
          <div className="filter-header">
            <h2>Filters</h2>
            {activeCount > 0 && (
              <button onClick={clearAll} className="filter-clear">
                Clear ({activeCount})
              </button>
            )}
          </div>

          <div className="filter-group">
            <p className="filter-label">Property age</p>
            <label>
              <input
                type="radio"
                name="age"
                checked={ageFilter === "all"}
                onChange={() => setAgeFilter("all")}
              />
              All
            </label>
            <label>
              <input
                type="radio"
                name="age"
                checked={ageFilter === "new"}
                onChange={() => setAgeFilter("new")}
              />
              New (0–5 yrs)
            </label>
            <label>
              <input
                type="radio"
                name="age"
                checked={ageFilter === "recent"}
                onChange={() => setAgeFilter("recent")}
              />
              Recent (6–15 yrs)
            </label>
            <label>
              <input
                type="radio"
                name="age"
                checked={ageFilter === "old"}
                onChange={() => setAgeFilter("old")}
              />
              Old (16+ yrs)
            </label>
          </div>

          <div className="filter-group">
            <p className="filter-label">Property Size</p>
            <label>
              <input
                type="radio"
                name="size"
                checked={sizeFilter === "all"}
                onChange={() => setSizeFilter("all")}
              />
              All
            </label>
            <label>
              <input
                type="radio"
                name="size"
                checked={sizeFilter === "small"}
                onChange={() => setSizeFilter("small")}
              />
              Small (&lt;800 sq ft)
            </label>
            <label>
              <input
                type="radio"
                name="size"
                checked={sizeFilter === "medium"}
                onChange={() => setSizeFilter("medium")}
              />
              Medium (800–1500 sq ft)
            </label>
            <label>
              <input
                type="radio"
                name="size"
                checked={sizeFilter === "large"}
                onChange={() => setSizeFilter("large")}
              />
              Large (&gt;1500 sq ft)
            </label>
          </div>
        </aside>

        <div className="results-area">
          {error && (
            <div className="error-message" role="alert">
              <p>{error}</p>
              <button type="button" onClick={() => setRetryCount((count) => count + 1)}>
                Try again
              </button>
            </div>
          )}

          {!error && !isLoading && (
            <div className="results-header">
              <p className="results-count">
                Showing <strong>{results.length}</strong> of {properties.length}{" "}
                properties in {selectedCity.label}
              </p>

              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="results-sort"
              >
                <option value="default">Best match</option>
                <option value="newest">Newest properties</option>
                <option value="oldest">Oldest properties</option>
                <option value="biggest">Largest properties</option>
              </select>
            </div>
          )}

          {isLoading && (
            <div className="property-grid">
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <div key={n} className="property-skeleton" />
              ))}
            </div>
          )}

          {!isLoading && !error && results.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon">🔎</div>
              <h3>No properties found for your selection</h3>
              <p>Try another location, search term, or clear one of the filters.</p>
            </div>
          )}
{!isLoading && !error && results.length > 0 && (
  <div className="property-grid">
    {results.map((p) => {
      const age = p.yearBuilt
        ? CURRENT_YEAR - p.yearBuilt
        : null;

      return (
        <Link
          to={`/properties/${p.id}`}
          key={p.id}
          className="property-card"
        >
          <div className="property-card-top">
            <h3>{p.name}</h3>

            <div className="property-card-badges">
              {p.propertyType && (
                <span className="badge badge-info">
                  {p.propertyType}
                </span>
              )}

              {age !== null && age <= 5 && (
                <span className="badge badge-success">
                  New
                </span>
              )}
            </div>
          </div>

          <p className="property-card-address">
            {p.address}, {p.city} {p.state} {p.zip}
          </p>

          <ul className="property-card-info">
            <li>{p.bedrooms} bedrooms</li>
            <li>{p.bathrooms} bathrooms</li>
            <li>{p.squareFootage} sq ft</li>
            {p.yearBuilt && <li>Built {p.yearBuilt}</li>}
          </ul>

          {p.totalUnits && (
            <p className="property-card-units">
              {p.totalUnits} units
            </p>
          )}
        </Link>
      );
    })}
  </div>
)}
        </div>
      </div>
    </div>
  );
}

export default SearchPage;