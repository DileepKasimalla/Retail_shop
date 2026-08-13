import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const links = [
  { to: "/", label: "Dashboard", icon: "▦", end: true },
  { to: "/customers", label: "Customers", icon: "☺", end: false },
  { to: "/items", label: "Items", icon: "🛒", end: false },
  { to: "/settings", label: "Settings", icon: "⚙", end: false },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="layout">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand">
          <span className="brand-mark">₹</span>
          <span className="brand-text">Shop Manager</span>
        </div>
        <nav className="nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              <span className="nav-icon">{l.icon}</span>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-chip">
            <span className="avatar">{user?.username?.[0]?.toUpperCase() ?? "?"}</span>
            <span className="user-name">{user?.username}</span>
          </div>
          <button className="btn btn-ghost btn-block" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            className="hamburger"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            ☰
          </button>
          <div className="topbar-title">Retail Shop Manager</div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>

      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}
    </div>
  );
}
