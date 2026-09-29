import { format, formatDistanceToNowStrict, parseISO } from "date-fns";

export function fmtDate(value: string | null | undefined, pattern = "dd MMM yyyy"): string {
  if (!value) return "—";
  return format(parseISO(value), pattern);
}

export function fmtDateTime(value: string | null | undefined): string {
  return fmtDate(value, "dd MMM yyyy, HH:mm");
}

export function fromNow(value: string | null | undefined): string {
  if (!value) return "—";
  return `${formatDistanceToNowStrict(parseISO(value))} ago`;
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function fmtNumber(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits }).format(n);
}

export function fmtINR(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (n >= 1e7) return `₹${fmtNumber(n / 1e7, 2)} Cr`;
  if (n >= 1e5) return `₹${fmtNumber(n / 1e5, 2)} L`;
  return `₹${fmtNumber(n)}`;
}

export function fmtTonnes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (Math.abs(n) >= 1e6) return `${fmtNumber(n / 1e6, 2)} Mt`;
  if (Math.abs(n) >= 1e3) return `${fmtNumber(n / 1e3, 1)} kt`;
  return `${fmtNumber(n)} t`;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral" | "violet";

export const outcomeTone: Record<string, Tone> = {
  compliant: "ok",
  minor_issues: "warn",
  non_compliant: "bad",
  pending: "neutral",
};

export const outcomeLabel: Record<string, string> = {
  compliant: "Compliant",
  minor_issues: "Minor Issues",
  non_compliant: "Non-Compliant",
  pending: "Pending",
};

export const severityTone: Record<string, Tone> = { low: "info", medium: "warn", high: "bad", critical: "bad" };

export const complianceTone: Record<string, Tone> = {
  compliant: "ok",
  due: "info",
  in_progress: "warn",
  overdue: "bad",
  violated: "bad",
};

export const violationTone: Record<string, Tone> = {
  open: "bad",
  escalated: "bad",
  action_assigned: "warn",
  pending_verification: "info",
  closed: "ok",
};

export const actionTone: Record<string, Tone> = {
  assigned: "info",
  in_progress: "warn",
  submitted: "violet",
  verified: "ok",
  rejected: "bad",
  overdue: "bad",
};

export const grievanceTone: Record<string, Tone> = {
  open: "bad",
  assigned: "info",
  in_progress: "warn",
  resolved: "violet",
  closed: "ok",
  rejected: "neutral",
};

export const bandTone: Record<string, Tone> = { low: "ok", moderate: "warn", high: "bad", critical: "bad" };

export const processingTone: Record<string, Tone> = {
  pending: "neutral",
  processing: "info",
  completed: "ok",
  failed: "bad",
};

export const roleLabel: Record<string, string> = {
  admin: "Administrator",
  corporate: "Corporate Management",
  mine_official: "Mine Official",
  regulator: "Regulator",
  contractor: "Contractor",
};

export function riskColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#94a3b8";
  if (score >= 80) return "#b91c1c";
  if (score >= 60) return "#dc3a3a";
  if (score >= 35) return "#d98a0b";
  return "#1f9d55";
}

export function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID().replace(/-/g, "");
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}
