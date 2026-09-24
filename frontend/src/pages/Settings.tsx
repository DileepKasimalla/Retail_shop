import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { User } from "../api/types";
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

      {user?.is_admin && <UsersCard currentUserId={user.id} />}
    </div>
  );
}

function UsersCard({ currentUserId }: { currentUserId: number }) {
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listUsers().then(setUsers).catch((err) => {
      setError(err instanceof ApiError ? err.message : "Could not load users");
    });
  }, []);

  function replace(updated: User) {
    setUsers((list) => list.map((u) => (u.id === updated.id ? updated : u)));
  }

  async function run(action: () => Promise<void>) {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function addUser(e: FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    run(async () => {
      const created = await api.createUser({ username: username.trim(), password, is_admin: isAdmin });
      setUsers((list) => [...list, created].sort((a, b) => a.username.localeCompare(b.username)));
      setSuccess(`Account '${created.username}' created. Share the password with them.`);
      setUsername("");
      setPassword("");
      setIsAdmin(false);
    });
  }

  function resetPassword(u: User) {
    const pw = window.prompt(`New password for ${u.username} (min 8 characters):`);
    if (pw === null) return;
    if (pw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    run(async () => {
      await api.updateUser(u.id, { password: pw });
      setSuccess(`Password reset for '${u.username}'.`);
    });
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-head">
        <h3>Users</h3>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Role</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {users.map((u) => {
            const self = u.id === currentUserId;
            return (
              <tr key={u.id}>
                <td>
                  {u.username}
                  {self && <span className="muted"> (you)</span>}
                </td>
                <td>
                  <span className={`badge ${u.is_admin ? "badge-info" : "badge-muted"}`}>
                    {u.is_admin ? "admin" : "staff"}
                  </span>
                </td>
                <td>
                  {u.is_active ? "Active" : <span className="badge badge-muted">disabled</span>}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {!self && (
                    <>
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={busy}
                        onClick={() => run(async () => replace(await api.updateUser(u.id, { is_admin: !u.is_admin })))}
                      >
                        {u.is_admin ? "Make staff" : "Make admin"}
                      </button>{" "}
                      <button
                        className={`btn btn-sm ${u.is_active ? "btn-danger-ghost" : "btn-ghost"}`}
                        disabled={busy}
                        onClick={() => run(async () => replace(await api.updateUser(u.id, { is_active: !u.is_active })))}
                      >
                        {u.is_active ? "Disable" : "Enable"}
                      </button>{" "}
                    </>
                  )}
                  <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => resetPassword(u)}>
                    Reset password
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <form onSubmit={addUser} className="form-grid" style={{ marginTop: 20 }}>
        <h4 className="full" style={{ margin: 0 }}>Add a user</h4>
        <label className="field">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" required />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
        <label className="checkbox full">
          <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
          Admin (can manage users)
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy}>
          Create user
        </button>
      </form>
    </div>
  );
}
