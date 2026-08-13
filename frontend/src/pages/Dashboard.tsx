import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { DashboardStats } from "../api/types";
import StatCard from "../components/StatCard";
import { money } from "../lib/format";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api
      .dashboard()
      .then((d) => active && setStats(d))
      .catch((e) => active && setError(e instanceof ApiError ? e.message : "Failed to load"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  if (loading) return <div className="spinner center" />;
  if (error) return <div className="alert alert-error">{error}</div>;
  if (!stats) return null;

  return (
    <div className="page">
      <div className="page-head">
        <h2>Dashboard</h2>
        <p className="muted">A quick view of your shop's dues and activity.</p>
      </div>

      <div className="stat-grid">
        <StatCard
          label="Total Outstanding"
          value={money(stats.total_outstanding)}
          hint="Money customers owe you"
          tone="danger"
          to="/customers?filter=debtors"
        />
        <StatCard
          label="Collected This Month"
          value={money(stats.collected_this_month)}
          hint="Payments received"
          tone="success"
          to="/customers"
        />
        <StatCard
          label="Debts This Month"
          value={money(stats.debts_this_month)}
          hint="Unpaid bills added"
          tone="info"
          to="/customers?filter=debtors"
        />
        <StatCard
          label="Customers"
          value={stats.active_customers}
          hint={`${stats.total_customers} total`}
          to="/customers"
        />
      </div>

      {stats.total_advance > 0 && (
        <div className="note-line">
          Advance balances held (customers who overpaid):{" "}
          <strong>{money(stats.total_advance)}</strong>
        </div>
      )}

      <div className="card">
        <div className="card-head">
          <h3>Top Debtors</h3>
          <Link to="/customers?filter=debtors" className="link">
            View all
          </Link>
        </div>
        {stats.top_debtors.length === 0 ? (
          <p className="empty">No outstanding dues. 🎉</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Customer</th>
                <th className="right">Owes</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_debtors.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link to={`/customers/${d.id}`} className="link">
                      {d.name}
                    </Link>
                  </td>
                  <td className="right amount-owe">{money(d.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
