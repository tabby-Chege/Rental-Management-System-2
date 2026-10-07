import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { getPropertyById, searchProperties } from "../../api/rentcastAPI";
import { normalizeProperty } from "../../utils/propertyAdapter";
import "./PropertyDetail.css";

const CURRENT_YEAR = new Date().getFullYear();

function PropertyDetailsPage() {
  const { id } = useParams();
  const [property, setProperty] = useState(null);
  const [related, setRelated] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;

    async function loadProperty() {
      setIsLoading(true);
      setError("");
      setProperty(null);
      setRelated([]);

      try {
        const data = await getPropertyById(id);
        if (ignore) return;
        if (!data) {
          setError("Property not found.");
          return;
        }

        const propertyData = normalizeProperty(data);
        setProperty(propertyData);

        try {
          const relatedData = await searchProperties(propertyData.city, propertyData.state);
          if (!ignore && Array.isArray(relatedData)) {
            setRelated(
              relatedData
                .map(normalizeProperty)
                .filter((item) => String(item.id) !== String(id))
                .slice(0, 3)
            );
          }
        } catch {
          // Related listings are optional; the requested property remains usable.
        }
      } catch (err) {
        if (!ignore) setError(err.message || "Could not load property.");
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }

    loadProperty();
    return () => {
      ignore = true;
    };
  }, [id]);

  if (isLoading) {
    return (
      <div className="details-page">
        <div className="details-skeleton details-skeleton-title" />
        <div className="details-skeleton details-skeleton-sub" />
        <div className="details-grid">
          <div className="details-skeleton details-skeleton-box" />
          <div className="details-skeleton details-skeleton-box" />
          <div className="details-skeleton details-skeleton-box" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="details-page">
        <Link to="/properties" className="details-back">
          ← Back to properties
        </Link>
        <p className="details-error">{error}</p>
      </div>
    );
  }

 const age = property.yearBuilt
  ? CURRENT_YEAR - property.yearBuilt
  : null;

  return (
    <div className="details-page">
      <Link to="/properties" className="details-back">
        ← Back to properties
      </Link>

      <header className="details-header">
  <div className="details-title">
    <h1>{property.name}</h1>

    <div className="details-badges">
      {age !== null && age <= 5 && (
        <span className="badge badge-info">New</span>
      )}
    </div>
  </div>

  <p className="details-address">
    📍 {property.address}, {property.city} {property.state} {property.zip}
  </p>
</header>

      <div className="details-grid">
       <section className="details-box">
  <h3>Overview</h3>
  <ul>
    <li>
      <span>Property type</span>
      <strong>{property.propertyType}</strong>
    </li>

    <li>
      <span>Bedrooms</span>
      <strong>{property.bedrooms}</strong>
    </li>

    <li>
      <span>Bathrooms</span>
      <strong>{property.bathrooms}</strong>
    </li>

    <li>
      <span>Square footage</span>
      <strong>
        {property.squareFootage !== "N/A"
          ? `${property.squareFootage} sq ft`
          : "N/A"}
      </strong>
    </li>

    <li>
      <span>Built</span>
      <strong>
        {property.yearBuilt ?? "N/A"}{" "}
        {age !== null && `(${age} yrs)`}
      </strong>
    </li>

    <li>
      <span>Total apartments</span>
      <strong>{property.totalUnits ?? "N/A"}</strong>
    </li>
  </ul>
</section>
      </div>

      {related.length > 0 && (
        <section className="details-related">
          <h2>Other properties in {property.city}</h2>
          <div className="related-grid">
            {related.map((p) => (
              <Link
                to={`/properties/${p.id}`}
                key={p.id}
                className="related-card"
              >
                <h3>{p.name}</h3>
                <p>{p.address}</p>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default PropertyDetailsPage;
