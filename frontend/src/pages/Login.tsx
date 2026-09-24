import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { user, login, setup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // null = still checking. True on a fresh install with no users yet.
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  useEffect(() => {
    api
      .setupStatus()
      .then((s) => setNeedsSetup(s.needs_setup))
      .catch(() => setNeedsSetup(false)); // fall back to the normal sign-in form
  }, []);

  // Already logged in? Bounce to the app.
  if (user) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (needsSetup) {
      if (password.length < 8) {
        setError("Password must be at least 8 characters.");
        return;
      }
      if (password !== confirm) {
        setError("Passwords do not match.");
        return;
      }
    }
    setSubmitting(true);
    try {
      if (needsSetup) {
        await setup(username.trim(), password);
      } else {
        await login(username.trim(), password);
      }
      navigate(from, { replace: true });
    } catch (err) {
      // Someone else finished setup first — switch to the normal sign-in.
      if (err instanceof ApiError && err.status === 409) setNeedsSetup(false);
      setError(err instanceof ApiError ? err.message : "Login failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (needsSetup === null) {
    return (
      <div className="app-loading">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand-mark big">₹</span>
          <h1>Shop Manager</h1>
          <p className="muted">
            {needsSetup
              ? "Welcome! Create the admin account to get started."
              : "Sign in to manage customers, bills and dues."}
          </p>
        </div>
        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="alert alert-error">{error}</div>}
          <label className="field">
            <span>Username</span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={needsSetup ? "new-password" : "current-password"}
              required
            />
          </label>
          {needsSetup && (
            <label className="field">
              <span>Confirm password</span>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                required
              />
            </label>
          )}
          <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
            {needsSetup
              ? submitting ? "Creating…" : "Create admin account"
              : submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
