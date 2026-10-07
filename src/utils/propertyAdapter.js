export function normalizeProperty(property) {
  return {
    id: property.id,
    name: property.formattedAddress || property.addressLine1 || "Unnamed Property",
    address:
      property.addressLine1 ||
      property.formattedAddress ||
      "Address unavailable",
    city: property.city || "",
    state: property.state || "",
    zip: property.zipCode || "",
    propertyType: property.propertyType || "Property",
    bedrooms: property.bedrooms ?? "N/A",
    bathrooms: property.bathrooms ?? "N/A",
    squareFootage: property.squareFootage ?? "N/A",
    yearBuilt: property.yearBuilt ?? null,
    totalUnits: property.features?.unitCount ?? null,
    latitude: property.latitude ?? null,
    longitude: property.longitude ?? null,
  };
}
