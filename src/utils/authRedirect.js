const FALLBACK_ORIGIN = "http://localhost";

export function safeReturnTo(value, origin = globalThis.location?.origin || FALLBACK_ORIGIN) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return null;
  }

  try {
    const base = new URL(origin);
    const target = new URL(value, base);
    if (target.origin !== base.origin) return null;
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return null;
  }
}
