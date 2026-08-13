import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "danger" | "success" | "info";
  to?: string; // if set, the whole card becomes a link
}

export default function StatCard({ label, value, hint, tone = "default", to }: StatCardProps) {
  const content = (
    <>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
      {to && <span className="stat-go">View →</span>}
    </>
  );

  if (to) {
    return (
      <Link to={to} className={`stat-card tone-${tone} clickable`}>
        {content}
      </Link>
    );
  }
  return <div className={`stat-card tone-${tone}`}>{content}</div>;
}
