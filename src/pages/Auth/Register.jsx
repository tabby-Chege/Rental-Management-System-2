import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { registerUser } from "../../api/authAPI";

function Register() {
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
    role: "landlord",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function handleChange(event) {
    setFormData({
      ...formData,
      [event.target.name]: event.target.value,
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (formData.password !== formData.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (
      formData.password.length < 10 ||
      !/[a-z]/.test(formData.password) ||
      !/[A-Z]/.test(formData.password) ||
      !/[0-9]/.test(formData.password) ||
      !/[^a-zA-Z0-9]/.test(formData.password)
    ) {
      setError(
        "Use at least 10 characters, including uppercase and lowercase letters, a number, and a symbol.",
      );
      return;
    }

    if (new TextEncoder().encode(formData.password).length > 72) {
      setError("Password must be no more than 72 UTF-8 bytes.");
      return;
    }

    setLoading(true);

    try {
      const response = await registerUser({
        name: formData.name.trim(),
        email: formData.email.trim(),
        password: formData.password,
        role: formData.role,
      });

      if (response.user?.role === "tenant") {
        navigate("/login", { replace: true });
      } else {
        navigate("/login", { replace: true });
      }
    } catch (err) {
      setError(err.message || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auth-page">
      <div className="auth-layout auth-layout--register">
        <aside className="auth-aside">
          <span className="auth-eyebrow">Welcome to Property Finder</span>
          <h2>Your next chapter starts at home.</h2>
          <p>
            Create an account to access rental tools tailored to the way you
            rent or manage property.
          </p>
          <ul className="auth-highlights">
            <li>Choose the account type that fits you</li>
            <li>Browse homes and follow applications</li>
            <li>Manage rental details from one workspace</li>
          </ul>
          <Link className="auth-aside-link" to="/properties">
            Browse available properties <span aria-hidden="true">→</span>
          </Link>
          <span className="auth-decoration auth-decoration--one" aria-hidden="true" />
          <span className="auth-decoration auth-decoration--two" aria-hidden="true" />
        </aside>

        <div className="auth-card">
          <span className="auth-card-kicker">Get started</span>
          <h1>Create your account</h1>
          <p className="auth-description">
            Register as a landlord or a tenant to access the right workflow.
          </p>

          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          <form onSubmit={handleSubmit}>
            <label htmlFor="name">Full name</label>
            <input
              id="name"
              name="name"
              type="text"
              value={formData.name}
              onChange={handleChange}
              autoComplete="name"
              placeholder="Your full name"
              required
            />

            <label htmlFor="email">Email address</label>
            <input
              id="email"
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              autoComplete="email"
              placeholder="you@example.com"
              required
            />

            <label htmlFor="role">Account type</label>
            <select
              id="role"
              name="role"
              value={formData.role}
              onChange={handleChange}
            >
              <option value="landlord">Landlord</option>
              <option value="tenant">Tenant</option>
            </select>

            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              value={formData.password}
              onChange={handleChange}
              autoComplete="new-password"
              minLength={10}
              maxLength={72}
              placeholder="Create a strong password"
              required
            />
            <p className="auth-password-hint">
              Use 10 or more characters with uppercase and lowercase letters, a
              number, and a symbol.
            </p>

            <label htmlFor="confirmPassword">Confirm password</label>
            <input
              id="confirmPassword"
              name="confirmPassword"
              type="password"
              value={formData.confirmPassword}
              onChange={handleChange}
              autoComplete="new-password"
              minLength={10}
              maxLength={72}
              placeholder="Enter your password again"
              required
            />

            <button type="submit" disabled={loading}>
              {loading ? "Creating account..." : "Create account"}
              {!loading && <span aria-hidden="true">→</span>}
            </button>
          </form>

          <p className="auth-switch">
            Already have an account? <Link to="/login">Log in</Link>
          </p>
        </div>
      </div>
    </section>
  );
}

export default Register;
