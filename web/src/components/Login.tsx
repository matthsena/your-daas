import { useState } from "react";
import { loginStep1, loginStep2, register } from "../control";

export function Login({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [ticket, setTicket] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [otpauth, setOtpauth] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submitRegister = async () => {
    setError(null);
    setBusy(true);
    try {
      const out = await register(username.trim().toLowerCase(), password);
      setSecret(out.totp_secret);
      setOtpauth(out.otpauth_url);
      setMode("login");
    } catch (e) {
      setError(e instanceof Error ? e.message : "registration failed");
    } finally {
      setBusy(false);
    }
  };

  const submitLogin = async () => {
    setError(null);
    setBusy(true);
    try {
      const out = await loginStep1(username.trim().toLowerCase(), password);
      setTicket(out.ticket);
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    } finally {
      setBusy(false);
    }
  };

  const submitTotp = async () => {
    if (!ticket) return;
    setError(null);
    setBusy(true);
    try {
      await loginStep2(ticket, code);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "invalid code");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-wrap">
      <section className="panel auth-panel">
        <h1>YourDaaS</h1>
        <p className="muted">Your PC in the browser. Sign in to reach your desktop.</p>
        <div className="row">
          <button
            type="button"
            className={mode === "login" ? "active" : ""}
            onClick={() => { setMode("login"); setError(null); }}
          >
            Sign in
          </button>
          <button
            type="button"
            className={mode === "register" ? "active" : ""}
            onClick={() => { setMode("register"); setError(null); }}
          >
            Register
          </button>
        </div>
        {mode === "register" ? (
          <>
            <label className="field">
              <span>Username (3–32 chars, a–z 0–9 _ -)</span>
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            </label>
            <label className="field">
              <span>Password (min 8 chars)</span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
            </label>
            <button type="button" disabled={busy || !username || !password} onClick={() => void submitRegister()}>
              Create account + desktop
            </button>
            <p className="muted">Registration provisions your private desktop container.</p>
          </>
        ) : ticket ? (
          <>
            <label className="field">
              <span>Authenticator code</span>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
              />
            </label>
            <button type="button" disabled={busy || !code} onClick={() => void submitTotp()}>
              Verify
            </button>
          </>
        ) : (
          <>
            <label className="field">
              <span>Username</span>
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            </label>
            <label className="field">
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                onKeyDown={(e) => { if (e.key === "Enter") void submitLogin(); }}
              />
            </label>
            <button type="button" disabled={busy || !username || !password} onClick={() => void submitLogin()}>
              Continue
            </button>
          </>
        )}
        {secret && (
          <div className="secret-box">
            <strong>Authenticator setup (shown once)</strong>
            <p className="muted">Enter this secret in your authenticator app, then sign in:</p>
            <code className="secret">{secret}</code>
            <p className="muted tiny">{otpauth}</p>
            <button type="button" onClick={() => { setSecret(null); setOtpauth(null); }}>
              Saved, continue
            </button>
          </div>
        )}
        {error && <p className="error">{error}</p>}
      </section>
    </main>
  );
}
