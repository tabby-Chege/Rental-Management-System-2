import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import QRCode from "qrcode";
import {
  prepareRequestOptions,
  serializeCredential,
} from "../../utils/webauthn";
import {
  beginTwoFactorSetup,
  beginPasskeyAuthentication,
  completeTwoFactor,
  completePasskeyAuthentication,
  loginUser,
  loginWithGoogle,
  sendLoginFactorCode,
  verifyLoginFactorCode,
  verifyRecoveryCode,
} from "../../api/authAPI";

function Login() {
  const navigate = useNavigate();
  const googleButtonRef = useRef(null);
  const totpQrRef = useRef(null);
  const googleCredentialHandler = useRef(null);
  const [googleScriptReady, setGoogleScriptReady] = useState(false);
  const [factorChallenge, setFactorChallenge] = useState(null);
  const [factorSetup, setFactorSetup] = useState(null);
  const [factorCode, setFactorCode] = useState("");
  const [selectedFactor, setSelectedFactor] = useState("totp");
  const [factorCodeRequested, setFactorCodeRequested] = useState(false);
  const [googleCredential, setGoogleCredential] = useState("");
  const [googleRole, setGoogleRole] = useState("landlord");
  const [googleRoleRequired, setGoogleRoleRequired] = useState(false);

  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

  useEffect(() => {
    if (!factorSetup?.provisioning_uri || !totpQrRef.current) return undefined;
    let cancelled = false;
    QRCode.toCanvas(totpQrRef.current, factorSetup.provisioning_uri, {
      width: 220,
      margin: 2,
      errorCorrectionLevel: "M",
      color: { dark: "#14251f", light: "#ffffff" },
    }).catch((qrError) => {
      if (!cancelled) {
        setError(qrError.message || "Could not display the authenticator QR code.");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [factorSetup]);

  useEffect(() => {
    if (!googleClientId) return undefined;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => setGoogleScriptReady(true);
    script.onerror = () => setError("Google sign-in could not be loaded.");
    document.head.appendChild(script);
    return () => script.remove();
  }, [googleClientId]);

  useEffect(() => {
    if (!googleScriptReady || !googleClientId || !googleButtonRef.current) return;
    const googleIdentity = window.google?.accounts?.id;
    if (!googleIdentity) return;
    googleIdentity.initialize({
      client_id: googleClientId,
      callback: (response) => googleCredentialHandler.current?.(response.credential),
    });
    googleIdentity.renderButton(googleButtonRef.current, {
      theme: "outline",
      size: "large",
      shape: "rectangular",
      text: "continue_with",
      width: Math.min(420, Math.floor(googleButtonRef.current.getBoundingClientRect().width)),
    });
  }, [googleClientId, googleScriptReady]);

  function finishSignIn(user) {
    if (user?.role === "tenant") {
      navigate("/tenant/details", { replace: true });
    } else {
      navigate("/manage/properties", { replace: true });
    }
  }

  async function handleFactorChallenge(response) {
    setFactorChallenge({
      token: response.challenge_token,
      setup: Boolean(response.mfa_setup_required),
      methods: response.methods || [],
    });
    setSelectedFactor(response.methods?.[0]?.id || "totp");
    setFactorCodeRequested(false);
    setFactorCode("");
    setFactorSetup(null);
    if (response.mfa_setup_required) {
      try {
        const setup = await beginTwoFactorSetup(response.challenge_token);
        setFactorSetup(setup);
      } catch (requestError) {
        setError(requestError.message || "Could not start authenticator setup.");
      }
    }
  }

  async function finishAuthentication(response) {
    if (response.mfa_required || response.mfa_setup_required) {
      await handleFactorChallenge(response);
      return;
    }
    finishSignIn(response.user);
  }

  async function handleGoogleCredential(credential, role) {
    if (!credential) {
      setError("Google did not return a sign-in credential.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const response = await loginWithGoogle(credential, role);
      if (response.role_required) {
        setGoogleCredential(credential);
        setGoogleRoleRequired(true);
        return;
      }
      await finishAuthentication(response);
    } catch (requestError) {
      setError(requestError.message || "Google sign-in failed.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    googleCredentialHandler.current = (credential) => {
      setGoogleCredential(credential);
      setGoogleRoleRequired(false);
      void handleGoogleCredential(credential);
    };
  });

  function handleChange(event) {
    setFormData({
      ...formData,
      [event.target.name]: event.target.value,
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await loginUser({
        email: formData.email.trim(),
        password: formData.password,
      });
      await finishAuthentication(response);
    } catch (err) {
      setError(err.message || "Login failed. Please check your details.");
    } finally {
      setLoading(false);
    }
  }

  async function handleFactorSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      let response;
      if (factorChallenge.setup || selectedFactor === "totp") {
        response = await completeTwoFactor(
          factorChallenge.token,
          factorCode.trim(),
          factorChallenge.setup,
        );
      } else if (selectedFactor === "recovery") {
        response = await verifyRecoveryCode(factorChallenge.token, factorCode.trim());
      } else {
        response = await verifyLoginFactorCode(
          factorChallenge.token,
          selectedFactor,
          factorCode.trim(),
        );
      }
      finishSignIn(response.user);
    } catch (requestError) {
      setError(requestError.message || "The authenticator code could not be verified.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendFactorCode() {
    setError("");
    setLoading(true);
    try {
      await sendLoginFactorCode(factorChallenge.token, selectedFactor);
      setFactorCodeRequested(true);
      setFactorCode("");
    } catch (requestError) {
      setError(requestError.message || "The verification code could not be sent.");
    } finally {
      setLoading(false);
    }
  }

  async function handlePasskeySignIn() {
    setError("");
    setLoading(true);
    try {
      if (!navigator.credentials?.get) {
        throw new Error("Passkeys are not supported by this browser.");
      }
      const { challenge_token: passkeyChallengeToken, options } =
        await beginPasskeyAuthentication(factorChallenge.token);
      const credential = await navigator.credentials.get({
        publicKey: prepareRequestOptions(options),
      });
      if (!credential) throw new Error("Passkey sign-in was cancelled.");
      const response = await completePasskeyAuthentication(
        factorChallenge.token,
        passkeyChallengeToken,
        serializeCredential(credential),
      );
      finishSignIn(response.user);
    } catch (requestError) {
      setError(requestError.message || "Passkey sign-in failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleRoleSubmit(event) {
    event.preventDefault();
    await handleGoogleCredential(googleCredential, googleRole);
  }

  return (
    <section className="auth-page">
      <div className="auth-layout">
        <aside className="auth-aside">
          <span className="auth-eyebrow">A better rental experience</span>
          <h2>Find your place. Manage it with confidence.</h2>
          <p>
            One simple space to explore homes, submit applications, and keep
            rental details in order.
          </p>
          <ul className="auth-highlights">
            <li>Explore available homes and units</li>
            <li>Keep your rental activity in one place</li>
            <li>Connect as a tenant or property manager</li>
          </ul>
          <Link className="auth-aside-link" to="/properties">
            Explore properties <span aria-hidden="true">→</span>
          </Link>
          <span className="auth-decoration auth-decoration--one" aria-hidden="true" />
          <span className="auth-decoration auth-decoration--two" aria-hidden="true" />
        </aside>

        <div className="auth-card">
          <span className="auth-card-kicker">
            {factorChallenge ? "Account protection" : "Your rental workspace"}
          </span>
          <h1>
            {factorChallenge
              ? factorChallenge.setup
                ? "Set up two-factor sign-in"
                : "Verify it’s you"
              : googleRoleRequired
                ? "Choose your account type"
                : "Welcome back"}
          </h1>
          <p className="auth-description">
            {factorChallenge
              ? factorChallenge.setup
                ? "Authenticator verification is required to protect every account."
                : "Enter the current code from your authenticator app to continue."
              : googleRoleRequired
                ? "Choose how you’ll use Property Finder. This will be your account type."
                : "Log in to continue to your rental workspace."}
          </p>

          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          {factorChallenge ? (
            <form onSubmit={handleFactorSubmit}>
              {factorChallenge.setup && factorSetup ? (
                <div className="auth-totp-setup">
                  <p>
                    Scan this QR code with an authenticator app, then enter the
                    6-digit code it generates. Keep the code and setup key private.
                  </p>
                  <canvas
                    ref={totpQrRef}
                    className="auth-totp-qr"
                    role="img"
                    aria-label="Authenticator setup QR code"
                  />
                  <p className="auth-totp-manual-label">
                    Can’t scan it? Enter this setup key manually:
                  </p>
                  <code>{factorSetup.secret}</code>
                  <p className="auth-totp-app-hint">
                    Compatible apps include Google Authenticator, Microsoft
                    Authenticator, and Authy.
                  </p>
                  <label htmlFor="factor-code">6-digit authenticator code</label>
                  <input
                    id="factor-code"
                    name="factorCode"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={factorCode}
                    onChange={(event) => setFactorCode(event.target.value.replace(/\D/g, ""))}
                    placeholder="000000"
                    required
                  />
                </div>
              ) : !factorChallenge.setup ? (
                <>
                  <fieldset className="auth-factor-options">
                    <legend>Choose a verification method</legend>
                    {factorChallenge.methods.map((method) => (
                      <button
                        type="button"
                        key={method.id}
                        className={selectedFactor === method.id ? "is-selected" : ""}
                        aria-pressed={selectedFactor === method.id}
                        onClick={() => {
                          setSelectedFactor(method.id);
                          setFactorCode("");
                          setFactorCodeRequested(false);
                        }}
                      >
                        {method.label}
                      </button>
                    ))}
                  </fieldset>
                  {selectedFactor === "passkey" ? (
                    <button
                      type="button"
                      onClick={handlePasskeySignIn}
                      disabled={loading}
                    >
                      {loading ? "Waiting for passkey..." : "Continue with passkey"}
                    </button>
                  ) : (
                    <>
                      {(selectedFactor === "email" || selectedFactor === "sms") && (
                        <button
                          type="button"
                          className="auth-secondary-button"
                          onClick={handleSendFactorCode}
                          disabled={loading}
                        >
                          {loading
                            ? "Sending..."
                            : factorCodeRequested
                              ? "Send another code"
                              : `Send ${selectedFactor === "sms" ? "text" : "email"} code`}
                        </button>
                      )}
                      {(selectedFactor === "totp" ||
                        selectedFactor === "recovery" ||
                        factorCodeRequested) && (
                        <>
                          <label htmlFor="factor-code">
                            {selectedFactor === "totp"
                              ? "6-digit authenticator code"
                              : selectedFactor === "recovery"
                                ? "Recovery code"
                                : "6-digit verification code"}
                          </label>
                          <input
                            id="factor-code"
                            name="factorCode"
                            type="text"
                            inputMode={selectedFactor === "recovery" ? "text" : "numeric"}
                            autoComplete="one-time-code"
                            pattern={selectedFactor === "recovery" ? undefined : "[0-9]{6}"}
                            maxLength={selectedFactor === "recovery" ? 64 : 6}
                            value={factorCode}
                            onChange={(event) => setFactorCode(
                              selectedFactor === "recovery"
                                ? event.target.value
                                : event.target.value.replace(/\D/g, ""),
                            )}
                            placeholder={selectedFactor === "recovery" ? "XXXX-XXXX-XXXX-XXXX" : "000000"}
                            required
                          />
                        </>
                      )}
                    </>
                  )}
                </>
              ) : (
                <p className="auth-password-hint" role="status">
                  Loading authenticator setup…
                </p>
              )}
              <button
                type="submit"
                disabled={
                  loading ||
                  (factorChallenge.setup && !factorSetup) ||
                  ((selectedFactor === "email" || selectedFactor === "sms") &&
                    !factorCodeRequested) ||
                  selectedFactor === "passkey"
                }
              >
                {loading
                  ? "Verifying..."
                  : factorChallenge.setup
                    ? "Enable two-factor sign-in"
                    : "Verify and log in"}
                {!loading && selectedFactor !== "passkey" && <span aria-hidden="true">→</span>}
              </button>
              <button
                type="button"
                className="auth-secondary-button"
                onClick={() => {
                  setFactorChallenge(null);
                  setFactorSetup(null);
                  setError("");
                }}
              >
                Use another sign-in method
              </button>
            </form>
          ) : googleRoleRequired ? (
            <form onSubmit={handleGoogleRoleSubmit}>
              <label htmlFor="google-role">Account type</label>
              <select
                id="google-role"
                value={googleRole}
                onChange={(event) => setGoogleRole(event.target.value)}
              >
                <option value="landlord">Landlord</option>
                <option value="tenant">Tenant</option>
              </select>
              <button type="submit" disabled={loading}>
                {loading ? "Continuing..." : "Continue with Google"}
                {!loading && <span aria-hidden="true">→</span>}
              </button>
            </form>
          ) : (
            <form onSubmit={handleSubmit}>
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

            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              value={formData.password}
              onChange={handleChange}
              autoComplete="current-password"
              placeholder="Enter your password"
              required
            />

            <button type="submit" disabled={loading}>
              {loading ? "Logging in..." : "Log in"}
              {!loading && <span aria-hidden="true">→</span>}
            </button>
            </form>
          )}

          {!factorChallenge && !googleRoleRequired && googleClientId && (
            <>
              <div className="auth-divider"><span>or</span></div>
              {googleScriptReady ? (
                <div className="google-signin-button" ref={googleButtonRef} />
              ) : (
                <p className="auth-password-hint" role="status">Loading Google sign-in…</p>
              )}
            </>
          )}

          {!factorChallenge && !googleRoleRequired && (
            <p className="auth-switch">
              Don't have an account? <Link to="/register">Create one</Link>
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

export default Login;
