function toFiniteNumber(value) {
  if (value == null || value === "") return Number.NaN;
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.NaN;
}

export function filterByLocation(properties, city, state, limit = 20) {
  const normalizedCity = city.toLowerCase();
  const normalizedState = state.toLowerCase();

  return properties
    .filter((property) =>
      String(property.city ?? "").toLowerCase() === normalizedCity &&
      String(property.state ?? "").toLowerCase() === normalizedState
    )
    .slice(0, limit);
}

export function filterProperties(
  properties,
  {
    query = "",
    ageFilter = "all",
    sizeFilter = "all",
    sortBy = "default",
    currentYear = new Date().getFullYear(),
  } = {}
) {
  const term = query.trim().toLowerCase();

  const matches = properties.filter((property) => {
    const matchesTerm = !term || [
      property.name,
      property.address,
      property.city,
      property.state,
      property.zip,
    ].some((value) => String(value ?? "").toLowerCase().includes(term));

    const builtYear = toFiniteNumber(property.yearBuilt);
    const hasBuildYear = Number.isFinite(builtYear);
    const age = currentYear - builtYear;
    const matchesAge = ageFilter === "all" || (
      hasBuildYear && (
        (ageFilter === "new" && age >= 0 && age <= 5) ||
        (ageFilter === "recent" && age > 5 && age <= 15) ||
        (ageFilter === "old" && age > 15)
      )
    );

    const squareFootage = toFiniteNumber(property.squareFootage);
    const hasSize = Number.isFinite(squareFootage);
    const matchesSize = sizeFilter === "all" || (
      hasSize && (
        (sizeFilter === "small" && squareFootage < 800) ||
        (sizeFilter === "medium" && squareFootage >= 800 && squareFootage <= 1500) ||
        (sizeFilter === "large" && squareFootage > 1500)
      )
    );

    return matchesTerm && matchesAge && matchesSize;
  });

  if (sortBy === "newest" || sortBy === "oldest") {
    const direction = sortBy === "newest" ? -1 : 1;
    return matches.sort((a, b) => {
      const aYear = toFiniteNumber(a.yearBuilt);
      const bYear = toFiniteNumber(b.yearBuilt);
      if (!Number.isFinite(aYear)) return Number.isFinite(bYear) ? 1 : 0;
      if (!Number.isFinite(bYear)) return -1;
      return (aYear - bYear) * direction;
    });
  }

  if (sortBy === "biggest") {
    return matches.sort((a, b) => {
      const aSize = toFiniteNumber(a.squareFootage);
      const bSize = toFiniteNumber(b.squareFootage);
      if (!Number.isFinite(aSize)) return Number.isFinite(bSize) ? 1 : 0;
      if (!Number.isFinite(bSize)) return -1;
      return bSize - aSize;
    });
  }

  return matches;
}