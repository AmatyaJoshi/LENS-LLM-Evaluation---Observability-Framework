import { formatDistanceToNowStrict } from "date-fns";

export function nsToDate(ns: number): Date {
  return new Date(Math.floor(ns / 1e6));
}

export function fmtTime(ns: number): string {
  const d = nsToDate(ns);
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function fmtDateTime(ns: number): string {
  const d = nsToDate(ns);
  return `${d.toLocaleDateString(undefined, { month: "short", day: "2-digit" })} ${d.toLocaleTimeString(
    undefined,
    { hour12: false },
  )}`;
}

export function fmtAgo(ns: number): string {
  if (!ns) return "never";
  try {
    return formatDistanceToNowStrict(nsToDate(ns), { addSuffix: true });
  } catch {
    return "";
  }
}

export function fmtMs(ms: number): string {
  if (!Number.isFinite(ms)) return "–";
  if (ms < 1) return `${(ms * 1000).toFixed(0)} µs`;
  if (ms < 1000) return `${ms < 10 ? ms.toFixed(1) : ms.toFixed(0)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

export function fmtInt(n: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
}

export function fmtCompact(n: number): string {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(
    n,
  );
}

export function fmtPct(x: number, digits = 1): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function fmtUsd(x: number): string {
  if (x === 0) return "$0.00";
  if (x < 0.01) return `$${x.toFixed(4)}`;
  return `$${x.toFixed(2)}`;
}

export function shortId(id: string, n = 8): string {
  return id.length > n ? id.slice(0, n) : id;
}

export function truncate(text: string, n: number): string {
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

export function stringify(value: unknown, pretty = true): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, pretty ? 2 : 0);
  } catch {
    return String(value);
  }
}
