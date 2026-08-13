let currencySymbol = "₹";

export function setCurrencySymbol(symbol: string): void {
  currencySymbol = symbol;
}

/** Format a number as Indian-grouped currency, e.g. 123456.5 -> "₹1,23,456.50". */
export function money(amount: number): string {
  const sign = amount < 0 ? "-" : "";
  const formatted = new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(amount));
  return `${sign}${currencySymbol}${formatted}`;
}

/** Format an ISO date (yyyy-mm-dd) as dd Mon yyyy. */
export function formatDate(iso: string): string {
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Format an ISO timestamp as a local time, e.g. "2:30 PM". */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

/** Today's date as yyyy-mm-dd in the user's local timezone. */
export function todayISO(): string {
  const d = new Date();
  const tz = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - tz).toISOString().slice(0, 10);
}
