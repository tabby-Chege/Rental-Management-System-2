import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getProperty } from "../../api/propertiesApi";
import "./PropertyDetail.css";

function PropertyDetailsPage() {
  const { id } = useParams();
  const [property, setProperty] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let ignore = false;

    async function loadProperty() {
      setIsLoading(true);
      setError("");
      try {
        const result = await getProperty(id);
        if (!ignore) setProperty(result);
      } catch (requestError) {
        if (!ignore) {
          setProperty(null);
          setError(requestError.message || "Could not load property.");
        }
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }

    loadProperty();
    return () => {
      ignore = true;
    };
  }, [id, retryCount]);

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
      <Link to="/manage/properties">Edit property records</Link>
    </div>
  );
}

export default PropertyDetailsPage;
