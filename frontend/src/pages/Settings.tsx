import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function SettingsPage() {
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (next.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      await api.changePassword(current, next);
      setSuccess("Password changed successfully.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change password");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h2>Settings</h2>
        <p className="muted">Signed in as {user?.username}</p>
      </div>

      <div className="card narrow">
        <div className="card-head">
          <h3>Change Password</h3>
        </div>
        <form onSubmit={submit} className="form-grid">
          {error && <div className="alert alert-error">{error}</div>}
          {success && <div className="alert alert-success">{success}</div>}
          <label className="field full">
            <span>Current password</span>
            <input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label className="field full">
            <span>New password</span>
            <input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
              required
            />
          </label>
          <label className="field full">
            <span>Confirm new password</span>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
            />
          </label>
          <button className="btn btn-primary" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Update password"}
          </button>
        </form>
      </div>
    </div>
  );
}
