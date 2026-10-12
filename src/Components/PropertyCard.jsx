import { Link } from "react-router-dom";

function PropertyCard({ property }) {
  const {
    id,
    formattedAddress,
    city,
    state,
    propertyType,
    bedrooms,
    bathrooms,
    squareFootage,
  } = property;

  // "123 Main St, Austin, TX 78701" -> "123 Main St"
  const street = formattedAddress ? formattedAddress.split(",")[0] : "Address unavailable";
  const location = [city, state].filter(Boolean).join(", ");

  return (
    <article className="property-card">
      <h3 className="property-card__title">{street}</h3>
      {location && <p className="property-card__location">{location}</p>}
      {propertyType && <span className="property-card__type">{propertyType}</span>}

      <ul className="property-card__stats">
        {bedrooms != null && <li>{bedrooms} bed</li>}
        {bathrooms != null && <li>{bathrooms} bath</li>}
        {squareFootage != null && <li>{squareFootage.toLocaleString()} sqft</li>}
      </ul>

      <Link className="property-card__link" to={`/properties/${encodeURIComponent(id)}`}>
        View details
      </Link>
    </article>
  );
}

export default PropertyCard;