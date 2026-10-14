import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import SearchBar from "../../Components/SearchBar/SearchBar";
import { listProperties } from "../../api/propertiesApi";
import "./SearchPage.css";

const PER_PAGE = 9;

function SearchPage() {
  const [properties, setProperties] = useState([]);
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
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
        const result = await listProperties({
          page,
          perPage: PER_PAGE,
          q: query,
          city,
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
  }, [page, query, city, retryCount]);

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
        <h1>Search my properties</h1>
        <p>Find your saved property records by name, address, or location.</p>
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

        {isLoading && <p className="status">Loading your properties...</p>}

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
            <p>Try another search or add a property to your portfolio.</p>
            <Link to="/manage/properties">Manage my properties</Link>
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
