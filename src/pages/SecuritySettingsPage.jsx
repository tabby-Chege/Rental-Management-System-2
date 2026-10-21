import { useCallback, useEffect, useState } from "react";
import {
  beginPasskeyRegistration,
  completePasskeyRegistration,
  generateRecoveryCodes,
  getFactorMethods,
  removePasskey,
  requestPhoneVerification,
  verifyPhoneNumber,
} from "../api/authAPI";
import { prepareCreationOptions, serializeCredential } from "../utils/webauthn";
import "./SecuritySettingsPage.css";

function SecuritySettingsPage() {
  const [settings, setSettings] = useState(null);
  const [phone, setPhone] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [phoneChallenge, setPhoneChallenge] = useState("");
  const [passkeyName, setPasskeyName] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadSettings = useCallback(async () => {
    try {
      setSettings(await getFactorMethods());
    } catch (requestError) {
      setError(requestError.message || "Security settings could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  async function handlePhoneRequest(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const response = await requestPhoneVerification(phone.trim());
      setPhoneChallenge(response.challenge_token);
      setMessage(response.message);
    } catch (requestError) {
      setError(requestError.message || "Could not send a verification text.");
    } finally {
      setLoading(false);
    }
  }

  async function handlePhoneVerify(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const response = await verifyPhoneNumber(phoneChallenge, phoneCode.trim());
      setMessage(`${response.message}: ${response.phone}`);
      setPhoneChallenge("");
      setPhoneCode("");
      setPhone("");
      await loadSettings();
    } catch (requestError) {
      setError(requestError.message || "The phone verification code was rejected.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAddPasskey() {
    setError("");
    setMessage("");
    setLoading(true);
    try {
      if (!navigator.credentials?.create) {
        throw new Error("Passkeys are not supported by this browser.");
      }
      const { challenge_token: challengeToken, options } =
        await beginPasskeyRegistration();
      const credential = await navigator.credentials.create({
        publicKey: prepareCreationOptions(options),
      });
      if (!credential) throw new Error("Passkey registration was cancelled.");
      await completePasskeyRegistration(
        challengeToken,
        serializeCredential(credential),
        passkeyName.trim() || "Passkey",
      );
      setPasskeyName("");
      setMessage("Passkey added to your account.");
      await loadSettings();
    } catch (requestError) {
      setError(requestError.message || "Could not register the passkey.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRemovePasskey(id) {
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const response = await removePasskey(id);
      setMessage(response.message);
      await loadSettings();
    } catch (requestError) {
      setError(requestError.message || "Could not remove the passkey.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateRecoveryCodes() {
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const response = await generateRecoveryCodes();
      setRecoveryCodes(response.codes);
      setMessage(response.message);
      await loadSettings();
    } catch (requestError) {
      setError(requestError.message || "Recovery codes could not be generated.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="security-settings-page">
      <header className="security-hero">
        <div className="security-hero-copy">
          <span className="security-eyebrow">ACCOUNT PROTECTION</span>
          <h1>Security settings</h1>
          <p>Manage your sign-in safeguards and recovery options in one place.</p>
          <div className="security-hero-badge">
            <span aria-hidden="true">✓</span>
            Authenticator verification is required
          </div>
        </div>
        <div className="security-hero-mark" aria-hidden="true">
          <svg viewBox="0 0 64 72" focusable="false">
            <path d="M32 3 57 12v19c0 17-10.5 29.5-25 37C17.5 60.5 7 48 7 31V12L32 3Z" />
            <path d="m21 35 7 7 15-16" />
          </svg>
        </div>
      </header>

      {error && <p className="auth-error" role="alert">{error}</p>}
      {message && <p className="security-success" role="status">{message}</p>}
      {!settings ? error ? (
        <div className="security-load-state">
          <p>Your security settings could not be loaded.</p>
          <button type="button" className="security-button" onClick={() => {
            setError("");
            void loadSettings();
          }}>
            Try again
          </button>
        </div>
      ) : (
        <p className="security-load-state" role="status">Loading your security settings…</p>
      ) : (
        <>
          <section className="security-methods-card" aria-label="Configured sign-in methods">
            <div className="security-section-heading">
              <div>
                <span className="security-eyebrow">YOUR SIGN-IN</span>
                <h2>Available verification methods</h2>
              </div>
              <span className="security-method-count">{settings.methods.length} active</span>
            </div>
            <div className="security-method-list">
              {settings.methods.map((method) => (
                <div className="security-method-chip" key={method.id}>
                  <span className={`security-method-icon is-${method.id}`} aria-hidden="true">
                    {method.id === "totp" ? "01" : method.id === "sms" ? "SMS" : method.id === "passkey" ? "PK" : method.id === "recovery" ? "RC" : "@"}
                  </span>
                  <span>{method.label}</span>
                  <span className="security-method-check" aria-label="Active">✓</span>
                </div>
              ))}
            </div>
            <p className="security-card-note">Your password is always protected by authenticator-app verification. Add a recovery option in case you lose access to a device.</p>
          </section>

          <div className="security-settings-grid">
            <section className="security-settings-card security-factor-card">
              <div className="security-card-title">
                <span className="security-card-icon" aria-hidden="true">SMS</span>
                <div>
                  <span className="security-eyebrow">PHONE BACKUP</span>
                  <h2>Text message verification</h2>
                </div>
              </div>
              {settings.sms_configured ? (
                <>
                  <p>
                    {settings.phone_verified
                      ? `Verified phone: ${settings.phone}`
                      : "Verify your phone number to use it for one-time sign-in codes."}
                  </p>
                  {!phoneChallenge ? (
                    <form onSubmit={handlePhoneRequest}>
                      <label htmlFor="mfa-phone">Phone number · international format</label>
                      <input
                        id="mfa-phone"
                        type="tel"
                        value={phone}
                        onChange={(event) => setPhone(event.target.value)}
                        placeholder="+254700000000"
                        autoComplete="tel"
                        required
                      />
                      <button className="security-button" type="submit" disabled={loading}>
                        {loading ? "Sending code…" : settings.phone_verified ? "Change phone number" : "Send verification code"}
                      </button>
                    </form>
                  ) : (
                    <form onSubmit={handlePhoneVerify}>
                      <label htmlFor="mfa-phone-code">6-digit text message code</label>
                      <input
                        id="mfa-phone-code"
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        pattern="[0-9]{6}"
                        maxLength={6}
                        value={phoneCode}
                        onChange={(event) => setPhoneCode(event.target.value.replace(/\D/g, ""))}
                        required
                      />
                      <div className="security-action-row">
                        <button className="security-button" type="submit" disabled={loading}>
                          {loading ? "Verifying…" : "Verify phone"}
                        </button>
                        <button className="security-button is-secondary" type="button" disabled={loading} onClick={() => {
                          setPhoneChallenge("");
                          setPhoneCode("");
                        }}>
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}
                </>
              ) : (
                <div className="security-provider-notice" role="status">
                  <strong>SMS isn’t set up on this server yet</strong>
                  <p>
                    Phone verification is unavailable until the administrator
                    configures Twilio credentials: account SID, auth token, and
                    sender number. Your other security methods remain available.
                  </p>
                </div>
              )}
            </section>

            <section className="security-settings-card security-factor-card">
              <div className="security-card-title">
                <span className="security-card-icon" aria-hidden="true">PK</span>
                <div>
                  <span className="security-eyebrow">DEVICE SIGN-IN</span>
                  <h2>Passkeys</h2>
                </div>
              </div>
              <p>Use your device screen lock, fingerprint, or a hardware security key to sign in.</p>
              {settings.passkeys.length > 0 ? (
                <div className="security-passkey-list">
                  {settings.passkeys.map((passkey) => (
                    <div className="security-passkey-row" key={passkey.id}>
                      <span>{passkey.name}</span>
                      <button
                        className="security-text-button"
                        type="button"
                        onClick={() => handleRemovePasskey(passkey.id)}
                        disabled={loading}
                        aria-label={`Remove ${passkey.name}`}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="security-inline-note">No passkeys added to this account.</p>
              )}
              <label htmlFor="passkey-name">Name this passkey (optional)</label>
              <input
                id="passkey-name"
                value={passkeyName}
                onChange={(event) => setPasskeyName(event.target.value)}
                maxLength={100}
                placeholder="e.g. My phone"
              />
              <button className="security-button" type="button" onClick={handleAddPasskey} disabled={loading}>
                {loading ? "Waiting for device…" : "Add a passkey"}
              </button>
            </section>

            <section className="security-settings-card security-factor-card security-recovery-card">
              <div className="security-card-title">
                <span className="security-card-icon" aria-hidden="true">RC</span>
                <div>
                  <span className="security-eyebrow">ACCOUNT RECOVERY</span>
                  <h2>Recovery codes</h2>
                </div>
              </div>
              <p>
                <strong>{settings.recovery_codes_remaining} unused</strong> · Each code works once.
                Generating a new set invalidates all previous codes.
              </p>
              <button className="security-button is-secondary" type="button" onClick={handleGenerateRecoveryCodes} disabled={loading}>
                {loading ? "Generating…" : "Generate new recovery codes"}
              </button>
              {recoveryCodes.length > 0 && (
                <div className="security-recovery-codes" role="region" aria-label="New recovery codes">
                  <p>Save these somewhere secure. They are only shown once.</p>
                  <ul>{recoveryCodes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </section>
  );
}

export default SecuritySettingsPage;
