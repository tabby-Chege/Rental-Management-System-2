import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import QRCode from "qrcode";
import {
  beginTwoFactorSetup,
  completeTwoFactor,
  beginGitHubLogin,
  getGitHubOAuthConfig,
  loginUser,
  loginWithGitHub,
  loginWithGoogle,
  sendLoginFactorCode,
  verifyLoginFactorCode,
  verifyRecoveryCode,
} from "../../api/authAPI";
import { safeReturnTo } from "../../utils/authRedirect.js";

function Login() {
  const location = useLocation();
  const navigate = useNavigate();
  const registrationChallenge = location.state?.registrationChallenge;
  const hasRegistrationChallenge =
    registrationChallenge?.flow === "registration" &&
    registrationChallenge?.factor_step === "email_otp" &&
    typeof registrationChallenge?.challenge_token === "string";
  const googleButtonRef = useRef(null);
  const totpQrRef = useRef(null);
  const googleCredentialHandler = useRef(null);
  const githubCallbackHandler = useRef(null);
  const [googleScriptReady, setGoogleScriptReady] = useState(false);
  const [githubOAuthAvailable, setGithubOAuthAvailable] = useState(false);
  const [factorChallenge, setFactorChallenge] = useState(() =>
    hasRegistrationChallenge
      ? {
          token: registrationChallenge.challenge_token,
          stage: registrationChallenge.factor_step,
          email: registrationChallenge.email,
          flow: "registration",
        }
      : null,
  );
  const [factorSetup, setFactorSetup] = useState(null);
  const [factorCode, setFactorCode] = useState("");
  const [recoveryMode, setRecoveryMode] = useState(false);
  const [factorCodeExpiresAt, setFactorCodeExpiresAt] = useState(() =>
    hasRegistrationChallenge
      ? Date.now() + (registrationChallenge.expires_in_seconds || 300) * 1000
      : null,
  );
  const [factorResendAvailableAt, setFactorResendAvailableAt] = useState(() =>
    hasRegistrationChallenge
      ? Date.now() + (registrationChallenge.resend_after_seconds || 30) * 1000
      : null,
  );
  const [challengeExpiresAt, setChallengeExpiresAt] = useState(() =>
    hasRegistrationChallenge
      ? Date.now() +
        (registrationChallenge.challenge_expires_in_seconds ||
          registrationChallenge.expires_in_seconds ||
          600) *
          1000
      : null,
  );
  const [currentTime, setCurrentTime] = useState(() =>
    hasRegistrationChallenge ? Date.now() : 0,
  );
  const [googleCredential, setGoogleCredential] = useState("");
  const [googleRole, setGoogleRole] = useState("landlord");
  const [githubRole, setGithubRole] = useState("landlord");
  const [googleRoleRequired, setGoogleRoleRequired] = useState(false);

  const [formData, setFormData] = useState({
    email: location.state?.email || "",
    password: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const [oauthCallbackError] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const providerError = params.get("error_description") || params.get("error");
    if (providerError) {
      return "GitHub sign-in was cancelled or could not be completed.";
    }
    if (
      code &&
      (!params.get("state") ||
        !sessionStorage.getItem("github_oauth_state") ||
        params.get("state") !== sessionStorage.getItem("github_oauth_state"))
    ) {
      return "The GitHub sign-in session is invalid or expired. Please try again.";
    }
    return "";
  });

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
    let cancelled = false;
    getGitHubOAuthConfig()
      .then(({ configured }) => {
        if (!cancelled) setGithubOAuthAvailable(configured === true);
      })
      .catch(() => {
        if (!cancelled) setGithubOAuthAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!factorChallenge) return undefined;
    const timer = window.setInterval(() => setCurrentTime(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [factorChallenge]);

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
    const returnTo =
      safeReturnTo(location.state?.returnTo) ||
      safeReturnTo(sessionStorage.getItem("login_return_to"));
    sessionStorage.removeItem("login_return_to");
    if (returnTo) {
      navigate(returnTo, { replace: true });
      return;
    }
    if (user?.role === "tenant") {
      navigate("/tenant/details", { replace: true });
    } else {
      navigate("/manage/properties", { replace: true });
    }
  }

  async function handleFactorChallenge(response) {
    const stage = response.factor_step;
    setFactorChallenge({
      token: response.challenge_token,
      stage,
      email: response.email,
      flow: response.flow,
    });
    setRecoveryMode(false);
    setFactorCode("");
    setFactorSetup(null);
    const now = Date.now();
    setFactorCodeExpiresAt(
      stage === "email_otp"
        ? now + (response.expires_in_seconds || 300) * 1000
        : null,
    );
    setFactorResendAvailableAt(
      stage === "email_otp"
        ? now + (response.resend_after_seconds || 30) * 1000
        : null,
    );
    setChallengeExpiresAt(
      now +
        (response.challenge_expires_in_seconds ||
          response.expires_in_seconds ||
          600) *
          1000,
    );
    setCurrentTime(now);
    if (stage === "authenticator_enrollment") {
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
    throw new Error("Complete both verification steps before signing in.");
  }

  function restartAuthentication() {
    setFactorChallenge(null);
    setFactorSetup(null);
    setFactorCode("");
    setRecoveryMode(false);
    setFactorCodeExpiresAt(null);
    setFactorResendAvailableAt(null);
    setChallengeExpiresAt(null);
    setError("");
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

  async function handleGitHubCredential(code, state, role) {
    setError("");
    setLoading(true);
    try {
      const response = await loginWithGitHub(code, state, role);
      await finishAuthentication(response);
    } catch (requestError) {
      setError(requestError.message || "GitHub sign-in failed.");
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
    githubCallbackHandler.current = (code, state, role) => {
      void handleGitHubCredential(code, state, role);
    };
  });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    const providerError = params.get("error_description") || params.get("error");
    if (!code && !providerError) return;

    const expectedState = sessionStorage.getItem("github_oauth_state");
    const role = sessionStorage.getItem("github_oauth_role") || "landlord";
    sessionStorage.removeItem("github_oauth_state");
    sessionStorage.removeItem("github_oauth_role");
    window.history.replaceState({}, "", window.location.pathname);
    if (providerError || !state || !expectedState || state !== expectedState) return;
    githubCallbackHandler.current?.(code, state, role);
  }, []);

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
      if (factorChallenge.stage === "email_otp") {
        const response = await verifyLoginFactorCode(
          factorChallenge.token,
          "email",
          factorCode.trim(),
        );
        await handleFactorChallenge(response);
      } else if (recoveryMode) {
        const response = await verifyRecoveryCode(
          factorChallenge.token,
          factorCode.trim(),
        );
        await handleFactorChallenge(response);
      } else {
        const response = await completeTwoFactor(
          factorChallenge.token,
          factorCode.trim(),
          factorChallenge.stage === "authenticator_enrollment",
        );
        finishSignIn(response.user);
      }
    } catch (requestError) {
      setError(
        requestError.message || "The verification code could not be verified.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSendFactorCode() {
    setError("");
    setLoading(true);
    try {
      const response = await sendLoginFactorCode(factorChallenge.token, "email");
      setFactorCode("");
      setCurrentTime(Date.now());
      setFactorCodeExpiresAt(Date.now() + (response.expires_in_seconds || 300) * 1000);
      setFactorResendAvailableAt(
        Date.now() + (response.resend_after_seconds || 30) * 1000,
      );
    } catch (requestError) {
      setError(requestError.message || "The verification code could not be sent.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleRoleSubmit(event) {
    event.preventDefault();
    await handleGoogleCredential(googleCredential, googleRole);
  }

  async function handleGitHubStart() {
    setError("");
    setLoading(true);
    try {
      const { authorization_url: authorizationUrl } = await beginGitHubLogin();
      const authorizationState = new URL(authorizationUrl).searchParams.get("state");
      if (!authorizationState) {
        throw new Error("GitHub sign-in could not be started.");
      }
      sessionStorage.setItem("github_oauth_state", authorizationState);
      sessionStorage.setItem("github_oauth_role", githubRole);
      const returnTo = safeReturnTo(location.state?.returnTo);
      if (returnTo) sessionStorage.setItem("login_return_to", returnTo);
      window.location.assign(authorizationUrl);
    } catch (requestError) {
      setError(requestError.message || "GitHub sign-in could not be started.");
      setLoading(false);
    }
  }

  const factorCodeExpired = (
    factorCodeExpiresAt !== null && currentTime >= factorCodeExpiresAt
  );
  const challengeExpired = (
    challengeExpiresAt !== null && currentTime >= challengeExpiresAt
  );
  const resendSeconds = factorResendAvailableAt
    ? Math.max(0, Math.ceil((factorResendAvailableAt - currentTime) / 1000))
    : 0;

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
            {factorChallenge
              ? factorChallenge.flow === "registration"
                ? "Account setup"
                : "Account protection"
              : "Your rental workspace"}
          </span>
          <h1>
            {factorChallenge
              ? factorChallenge.stage === "email_otp"
                ? "Step 2 of 3: Verify your email"
                : factorChallenge.stage === "authenticator_enrollment"
                  ? "Step 3 of 3: Set up your authenticator"
                  : recoveryMode
                    ? "Recover your authenticator"
                    : "Step 3 of 3: Enter your authenticator code"
              : googleRoleRequired
                ? "Choose your account type"
                : "Welcome back"}
          </h1>
          <p className="auth-description">
            {factorChallenge
              ? factorChallenge.stage === "email_otp"
                ? `Enter the one-time code sent to ${factorChallenge.email}.`
                : factorChallenge.stage === "authenticator_enrollment"
                  ? "Your email is verified. Register an authenticator app before continuing."
                  : recoveryMode
                    ? "Enter one unused recovery code. You will need to register a new authenticator before access is restored."
                    : "Your email is verified. Enter the current six-digit code from your authenticator app."
              : googleRoleRequired
                ? "Choose how you’ll use Property Finder. This will be your account type."
                : "Log in to continue to your rental workspace."}
          </p>
          {factorChallenge?.flow === "registration" && (
            <p className="auth-password-hint" role="status">
                Your account is created but not active yet. Complete email
                verification and authenticator setup now, or sign in later to
                resume the required steps.
            </p>
          )}

          {factorChallenge && (
            <ol className="auth-factor-progress" aria-label="Sign-in progress">
              <li>Credentials</li>
              <li aria-current={factorChallenge.stage === "email_otp" ? "step" : undefined}>
                Email code
              </li>
              <li
                aria-current={
                  factorChallenge.stage !== "email_otp" ? "step" : undefined
                }
              >
                Authenticator
              </li>
            </ol>
          )}

          {(error || oauthCallbackError) && (
            <p className="auth-error" role="alert">
              {error || oauthCallbackError}
            </p>
          )}

          {factorChallenge ? (
            <form onSubmit={handleFactorSubmit}>
              {challengeExpired ? (
                <>
                  <p className="auth-password-hint" role="status">
                    This verification session has expired. Start again with your email and password.
                  </p>
                  <button
                    type="button"
                    className="auth-secondary-button"
                    onClick={restartAuthentication}
                  >
                    Return to sign in
                  </button>
                </>
              ) : factorChallenge.stage === "email_otp" ? (
                <>
                  <p className="auth-password-hint" role="status">
                    {factorCodeExpired
                      ? "This email code has expired. Request a new code to continue."
                      : `The code expires in ${Math.max(
                          0,
                          Math.ceil((factorCodeExpiresAt - currentTime) / 60000),
                        )} minute(s).`}
                  </p>
                  <label htmlFor="factor-code">Six-digit email verification code</label>
                  <input
                    id="factor-code"
                    name="factorCode"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={factorCode}
                    onChange={(event) =>
                      setFactorCode(event.target.value.replace(/\D/g, ""))
                    }
                    placeholder="000000"
                    required
                  />
                  <button
                    type="button"
                    className="auth-secondary-button"
                    onClick={handleSendFactorCode}
                    disabled={loading || resendSeconds > 0}
                  >
                    {loading
                      ? "Sending..."
                      : resendSeconds > 0
                        ? `Resend available in ${resendSeconds}s`
                        : "Resend email code"}
                  </button>
                </>
              ) : factorChallenge.stage === "authenticator_enrollment" && factorSetup ? (
                <div className="auth-totp-setup">
                  <p>
                    Scan this QR code with an authenticator app, then enter the
                    six-digit code it generates. Keep the setup key private.
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
                    Compatible apps include Google Authenticator and Microsoft
                    Authenticator.
                  </p>
                  <label htmlFor="factor-code">Six-digit authenticator-app code</label>
                  <input
                    id="factor-code"
                    name="factorCode"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={factorCode}
                    onChange={(event) =>
                      setFactorCode(event.target.value.replace(/\D/g, ""))
                    }
                    placeholder="000000"
                    required
                  />
                </div>
              ) : factorChallenge.stage === "authenticator_totp" ? (
                <>
                  <p className="auth-password-hint" role="status">
                    This authenticator challenge expires in{" "}
                    {Math.max(
                      0,
                      Math.ceil((challengeExpiresAt - currentTime) / 60000),
                    )}{" "}
                    minute(s).
                  </p>
                  {!recoveryMode && (
                    <>
                      <label htmlFor="factor-code">Six-digit authenticator-app code</label>
                      <input
                        id="factor-code"
                        name="factorCode"
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        pattern="[0-9]{6}"
                        maxLength={6}
                        value={factorCode}
                        onChange={(event) =>
                          setFactorCode(event.target.value.replace(/\D/g, ""))
                        }
                        placeholder="000000"
                        required
                      />
                      <button
                        type="button"
                        className="auth-secondary-button"
                        onClick={() => {
                          setRecoveryMode(true);
                          setFactorCode("");
                          setError("");
                        }}
                      >
                        Lost your authenticator? Use a recovery code
                      </button>
                    </>
                  )}
                  {recoveryMode && (
                    <>
                      <label htmlFor="factor-code">Unused recovery code</label>
                      <input
                        id="factor-code"
                        name="factorCode"
                        type="text"
                        autoComplete="one-time-code"
                        maxLength={64}
                        value={factorCode}
                        onChange={(event) => setFactorCode(event.target.value)}
                        placeholder="XXXX-XXXX-XXXX-XXXX"
                        required
                      />
                      <button
                        type="button"
                        className="auth-secondary-button"
                        onClick={() => {
                          setRecoveryMode(false);
                          setFactorCode("");
                          setError("");
                        }}
                      >
                        Return to authenticator code
                      </button>
                    </>
                  )}
                </>
              ) : (
                <p className="auth-password-hint" role="status">
                  Loading authenticator enrollment…
                </p>
              )}
              {!challengeExpired && (
                <button
                  type="submit"
                  disabled={
                    loading ||
                    (factorChallenge.stage === "email_otp" && factorCodeExpired) ||
                    (factorChallenge.stage === "authenticator_enrollment" &&
                      !factorSetup)
                  }
                >
                  {loading
                    ? "Verifying..."
                    : factorChallenge.stage === "email_otp"
                      ? "Verify email and continue"
                      : factorChallenge.stage === "authenticator_enrollment"
                        ? "Enable authenticator and sign in"
                        : recoveryMode
                          ? "Verify recovery code"
                          : "Verify authenticator and sign in"}
                  {!loading && <span aria-hidden="true">→</span>}
                </button>
              )}
              {challengeExpired && (
                <button
                  type="button"
                  className="auth-secondary-button"
                  onClick={() => {
                    setFactorChallenge(null);
                    setFactorSetup(null);
                    setFactorCode("");
                    setFactorCodeExpiresAt(null);
                    setFactorResendAvailableAt(null);
                    setChallengeExpiresAt(null);
                    setRecoveryMode(false);
                    setError("");
                  }}
                >
                  Start sign-in again
                </button>
              )}
              <button
                type="button"
                className="auth-secondary-button"
                onClick={() => {
                  setFactorChallenge(null);
                  setFactorSetup(null);
                  setFactorCodeExpiresAt(null);
                  setFactorResendAvailableAt(null);
                  setChallengeExpiresAt(null);
                  setRecoveryMode(false);
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

          {!factorChallenge &&
            !googleRoleRequired &&
            (googleClientId || githubOAuthAvailable) && (
            <>
              <div className="auth-divider"><span>or</span></div>
              {googleClientId && (googleScriptReady ? (
                <div className="google-signin-button" ref={googleButtonRef} />
              ) : (
                <p className="auth-password-hint" role="status">Loading Google sign-in…</p>
              ))}
              {githubOAuthAvailable && (
                <>
                  <label htmlFor="github-role">Account type for a new GitHub account</label>
                  <select
                    id="github-role"
                    value={githubRole}
                    onChange={(event) => setGithubRole(event.target.value)}
                  >
                    <option value="landlord">Landlord</option>
                    <option value="tenant">Tenant</option>
                  </select>
                  <button
                    type="button"
                    className="auth-secondary-button"
                    onClick={handleGitHubStart}
                    disabled={loading}
                  >
                    {loading ? "Opening GitHub…" : "Continue with GitHub"}
                  </button>
                </>
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
