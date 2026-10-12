import { useState, useEffect } from "react";
import "./SearchBar.css";

function SearchBar({ onSearch, isLoading }) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      onSearch(query);
    }, 400);
    return () => clearTimeout(timer);
  }, [query, onSearch]);

  function handleClear() {
    setQuery("");
  }

  return (
    <div className="search-bar">
      <span className="search-bar-icon" aria-hidden="true">🔍</span>

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search properties, addresses, or zips..."
        className="search-bar-input"
        aria-label="Search properties"
      />

      {isLoading && <span className="search-bar-spinner" aria-label="Loading" />}

      {query && !isLoading && (
        <button
          type="button"
          className="search-bar-clear"
          onClick={handleClear}
          aria-label="Clear search"
        >
          ×
        </button>
      )}
    </div>
  );
}

export default SearchBar;