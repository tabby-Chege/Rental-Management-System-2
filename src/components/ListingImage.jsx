import { useState } from "react";

function ListingImage({
  src,
  alt,
  className = "",
  fallbackClassName = "listing-image-unavailable",
}) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div
        className={fallbackClassName}
        role="img"
        aria-label={`${alt}: image unavailable`}
      >
        <span aria-hidden="true">⌂</span>
        <small>Image unavailable</small>
      </div>
    );
  }

  return (
    <img
      className={className}
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

export default ListingImage;
