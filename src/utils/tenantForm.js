export function validateTenantForm({ name, email, phone }, { requireName = true } = {}) {
  const errors = {};
  if (requireName && !name.trim()) errors.name = "Name is required.";

  const cleanEmail = email.trim();
  const domain = cleanEmail.split("@")[1] ?? "";
  if (!cleanEmail.includes("@") || !domain.includes(".")) {
    errors.email = "Enter a valid email address.";
  }

  if (phone.trim() && !/^[0-9+()\-\s]{7,30}$/.test(phone.trim())) {
    errors.phone = "Phone can only contain digits, spaces, + ( ) and -.";
  }
  return errors;
}
