const FALLBACK_CURRENCIES = `
  AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND
  BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUC CUP CVE CZK
  DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
  HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF
  KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP
  MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP
  PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS
  SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD
  UYU UZS VES VND VUV WST XAF XCD XCG XDR XOF XPF XSU YER ZAR ZMW ZWG ZWL
`.trim().split(/\s+/);

export const CURRENCY_CODES = (
  typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("currency")
    : FALLBACK_CURRENCIES
).filter((currency) => currency !== "XXX");

export function formatMoney(amount, currency) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  }).format(Number(amount));
}

export function currencyPrecision(currency) {
  if (!currency) return 2;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  }).resolvedOptions().maximumFractionDigits;
}

export function phoneParts(phone) {
  const country = PHONE_COUNTRIES
    .filter(({ dialCode }) => phone?.startsWith(dialCode))
    .sort((a, b) => b.dialCode.length - a.dialCode.length)[0];
  if (!country) return { dialCode: "custom", number: phone ?? "" };
  return {
    dialCode: country.dialCode,
    number: phone.slice(country.dialCode.length).replace(/^0/, ""),
  };
}

export function makeInternationalPhone(dialCode, number) {
  if (dialCode === "custom") return String(number ?? "").trim() || null;
  const digits = String(number ?? "").replace(/\D/g, "").replace(/^0+/, "");
  return digits ? `${dialCode}${digits}` : null;
}

export const PHONE_COUNTRIES = [
  { code: "AU", name: "Australia", dialCode: "+61", currency: "AUD" },
  { code: "BR", name: "Brazil", dialCode: "+55", currency: "BRL" },
  { code: "CA", name: "Canada", dialCode: "+1", currency: "CAD" },
  { code: "CN", name: "China", dialCode: "+86", currency: "CNY" },
  { code: "FR", name: "France", dialCode: "+33", currency: "EUR" },
  { code: "DE", name: "Germany", dialCode: "+49", currency: "EUR" },
  { code: "GH", name: "Ghana", dialCode: "+233", currency: "GHS" },
  { code: "IN", name: "India", dialCode: "+91", currency: "INR" },
  { code: "IE", name: "Ireland", dialCode: "+353", currency: "EUR" },
  { code: "IT", name: "Italy", dialCode: "+39", currency: "EUR" },
  { code: "JP", name: "Japan", dialCode: "+81", currency: "JPY" },
  { code: "KE", name: "Kenya", dialCode: "+254", currency: "KES" },
  { code: "MX", name: "Mexico", dialCode: "+52", currency: "MXN" },
  { code: "NL", name: "Netherlands", dialCode: "+31", currency: "EUR" },
  { code: "NG", name: "Nigeria", dialCode: "+234", currency: "NGN" },
  { code: "PK", name: "Pakistan", dialCode: "+92", currency: "PKR" },
  { code: "PH", name: "Philippines", dialCode: "+63", currency: "PHP" },
  { code: "PL", name: "Poland", dialCode: "+48", currency: "PLN" },
  { code: "PT", name: "Portugal", dialCode: "+351", currency: "EUR" },
  { code: "RW", name: "Rwanda", dialCode: "+250", currency: "RWF" },
  { code: "SA", name: "Saudi Arabia", dialCode: "+966", currency: "SAR" },
  { code: "ZA", name: "South Africa", dialCode: "+27", currency: "ZAR" },
  { code: "KR", name: "South Korea", dialCode: "+82", currency: "KRW" },
  { code: "ES", name: "Spain", dialCode: "+34", currency: "EUR" },
  { code: "SE", name: "Sweden", dialCode: "+46", currency: "SEK" },
  { code: "CH", name: "Switzerland", dialCode: "+41", currency: "CHF" },
  { code: "TZ", name: "Tanzania", dialCode: "+255", currency: "TZS" },
  { code: "TH", name: "Thailand", dialCode: "+66", currency: "THB" },
  { code: "UG", name: "Uganda", dialCode: "+256", currency: "UGX" },
  { code: "AE", name: "United Arab Emirates", dialCode: "+971", currency: "AED" },
  { code: "GB", name: "United Kingdom", dialCode: "+44", currency: "GBP" },
  { code: "US", name: "United States", dialCode: "+1", currency: "USD" },
];

export const PROPERTY_COUNTRIES = PHONE_COUNTRIES
  .map(({ code, name }) => ({ code, name }))
  .sort((a, b) => a.name.localeCompare(b.name));

export function currencyForCountry(countryCode) {
  return PHONE_COUNTRIES.find(({ code }) => code === countryCode)?.currency;
}
