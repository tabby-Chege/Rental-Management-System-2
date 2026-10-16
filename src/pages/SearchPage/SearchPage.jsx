import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import SearchBar from "../../Components/SearchBar/SearchBar";
import { listPublicProperties } from "../../api/propertiesApi";
import "./SearchPage.css";

const PER_PAGE = 9;

function SearchPage() {
  const [properties, setProperties] = useState([]);
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [minRent, setMinRent] = useState("");
  const [maxRent, setMaxRent] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [available, setAvailable] = useState("");
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
        const result = await listPublicProperties({
          page,
          perPage: PER_PAGE,
          q: query,
          city,
          minRent,
          maxRent,
          bedrooms,
          available,
        });
        if (!ignore) {
          setProperties(result.properties);
          setPagination(result.pagination);
        }
      } catch (requestError) {
        if (!ignore) {
          setProperties([]);
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
  }, [page, query, city, minRent, maxRent, bedrooms, available, retryCount]);

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
        <h1>Find a rental property</h1>
        <p>Browse listings from property managers and narrow them by location and unit details.</p>
      </header>

      <div className="search-page-searchbar">
        <SearchBar onSearch={updateSearch} isLoading={isLoading} />
      </div>

      <div className="search-location">
        <label htmlFor="property-city">City</label>
        <input
          id="property-city"
          type="search"
          value={city}
          onChange={updateCity}
          placeholder="All cities"
          maxLength={100}
        />
      </div>

      <div className="search-filters" aria-label="Property filters">
        <label>
          Minimum rent
          <input
            type="number"
            min="0"
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
                {count === 0 ? "Studio" : `${count}+`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Availability
          <select
            value={available}
            onChange={(event) => {
              setAvailable(event.target.value);
              setPage(1);
            }}
          >
            <option value="">Any</option>
            <option value="true">Available</option>
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

        {isLoading && <p className="status">Loading properties...</p>}

        {!isLoading && !error && pagination && (
          <div className="results-header">
            <p className="results-count">
              Showing {properties.length} of {pagination.total} properties
            </p>
          </div>
        )}

        {!isLoading && !error && properties.length === 0 && (
          <div className="empty-state">
            <h2>No properties found</h2>
            <p>Try a different city, price range, or bedroom count.</p>
            <Link to="/register">Create an account</Link>
          </div>
        )}

        {!isLoading && !error && properties.length > 0 && (
          <div className="property-grid">
            {properties.map((property) => (
              <Link
                to={`/properties/${property.id}`}
                key={property.id}
                className="property-card"
              >
                <div className="property-card-top">
                  <h2>{property.name}</h2>
                </div>
                <p className="property-card-address">
                  {property.address}, {property.city}, {property.state}
                  {property.zip_code ? ` ${property.zip_code}` : ""}
                </p>
                {property.description && <p>{property.description}</p>}
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
