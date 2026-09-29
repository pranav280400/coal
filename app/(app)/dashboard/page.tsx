"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  ChartSpline,
  ChevronDown,
  ClipboardList,
  CloudSun,
  Factory,
  FileText,
  HardHat,
  Leaf,
  MessageSquareText,
  Search,
  Sparkles,
  TriangleAlert,
  Users,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Shiny, Split } from "@/components/fx";
import { MineMap } from "@/components/map";
import { AnimatedList, CountUp, CountUpText, GrowBar, Stagger, StaggerItem, useSpotlight } from "@/components/motion";
import { useSession } from "@/components/session";
import { Badge, cn, ErrorState } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtNumber, humanize, outcomeLabel, outcomeTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { DashboardSummary, EnvSummary, GrievanceSummary, ProductionSummary } from "@/lib/types";

// ------------------------------------------------------------------ period
type PeriodKey = "this_month" | "last_month" | "last_3_months" | "this_fy";
const PERIODS: { key: PeriodKey; label: string }[] = [
  { key: "this_month", label: "This month" },
  { key: "last_month", label: "Last month" },
  { key: "last_3_months", label: "Last 3 months" },
  { key: "this_fy", label: "This financial year" },
];

function periodRange(key: PeriodKey): [Date, Date] {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  switch (key) {
    case "last_month":
      return [new Date(y, m - 1, 1), new Date(y, m, 0)];
    case "last_3_months":
      return [new Date(y, m - 2, 1), new Date(y, m + 1, 0)];
    case "this_fy": {
      const start = m >= 3 ? y : y - 1;
      return [new Date(start, 3, 1), new Date(start + 1, 2, 31)];
    }
    default:
      return [new Date(y, m, 1), new Date(y, m + 1, 0)];
  }
}

const long = (d: Date) => d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function PeriodPicker({ value, onChange }: { value: PeriodKey; onChange: (k: PeriodKey) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [from, to] = periodRange(value);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={t("Report period")}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="inline-flex h-11 items-center gap-2.5 rounded-xl border border-fg/10 bg-fg/[0.04] px-3.5 text-sm text-ink backdrop-blur transition hover:border-fg/20"
      >
        <CalendarDays className="h-4 w-4 text-copper-400" aria-hidden />
        {long(from)} – {long(to)}
        <ChevronDown className={cn("h-4 w-4 text-steel-500 transition", open && "rotate-180")} />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
            <motion.ul
              role="listbox"
              initial={{ opacity: 0, y: -6, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.97 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 z-40 mt-2 w-60 origin-top-right rounded-2xl border border-fg/10 bg-raised/95 p-1.5 shadow-[0_24px_60px_-20px_rgb(0_0_0/0.9)] backdrop-blur-xl"
            >
              {PERIODS.map((p) => (
                <li key={p.key}>
                  <button
                    role="option"
                    aria-selected={p.key === value}
                    onClick={() => { onChange(p.key); setOpen(false); }}
                    className={cn("w-full rounded-xl px-3 py-2.5 text-left text-sm transition hover:bg-fg/5", p.key === value ? "bg-copper-500/12 font-semibold text-copper-300" : "text-steel-600")}
                  >
                    {t(p.label)}
                  </button>
                </li>
              ))}
            </motion.ul>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good Morning" : h < 17 ? "Good Afternoon" : "Good Evening";
}

// ------------------------------------------------------------------- hero
function HeroBand({ name, scope, coords, rate, children }: {
  name: string; scope: string | null; coords: { lat: number; lon: number } | null; rate: number; children: ReactNode;
}) {
  const { t } = useI18n();
  const { data: weather } = useQuery({
    queryKey: ["weather", coords?.lat, coords?.lon],
    queryFn: () => fetch(`/api/weather?lat=${coords!.lat}&lon=${coords!.lon}`).then((r) => (r.ok ? r.json() : null)),
    enabled: !!coords,
    staleTime: 15 * 60_000,
  });
  const first = name.split(" ")[0];
  return (
    <section className="relative isolate overflow-hidden rounded-[28px] border border-fg/[0.07] bg-surface px-5 py-6 sm:px-8 sm:py-8">
      {/* copper light + dot grid, all CSS — no WebGL inside the app */}
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(700px_320px_at_85%_-20%,rgb(212_136_78/0.28),transparent_70%),radial-gradient(500px_260px_at_0%_120%,rgb(106_162_255/0.08),transparent_70%)]" />
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(var(--dot)_1px,transparent_1px)] bg-[size:18px_18px] [mask-image:linear-gradient(to_left,black,transparent_70%)]" />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 rounded-full border border-fg/10 bg-fg/[0.04] px-3 py-1 text-xs">
              <span className="h-1.5 w-1.5 rounded-full bg-ok shadow-[0_0_8px_#34c77b] motion-safe:animate-pulse" />
              <Shiny text={t("Live · refreshed every minute")} />
            </span>
            {weather && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-fg/10 bg-fg/[0.04] px-3 py-1 text-xs text-steel-600">
                <CloudSun className="h-3.5 w-3.5 text-warn" /> {weather.temperature_c}°C · {weather.condition}
              </span>
            )}
          </div>
          <p className="mt-5 text-[15px] text-muted">{t(greeting())},</p>
          <h1 className="font-display text-[34px] leading-[1.05] font-bold tracking-[-0.035em] text-ink sm:text-[46px]">
            <Split text={first} by="chars" delay={30} />
            <span className="text-copper-400">.</span>
          </h1>
          <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-muted">
            {scope ? `${scope} · ` : ""}
            {t("Compliance is at {n}% across your scope.", { n: Math.round(rate) })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">{children}</div>
      </div>
    </section>
  );
}

// -------------------------------------------------------------- KPI tiles
function Kpi({ icon, tone, label, value, foot, footTone = "text-ok", href, className }: {
  icon: ReactNode; tone: string; label: string; value: string; foot: string; footTone?: string; href: string; className?: string;
}) {
  const { t } = useI18n();
  const { handlers, layer } = useSpotlight("rgba(212, 136, 78, 0.12)");
  return (
    <StaggerItem className={className}>
      <Link
        href={href}
        {...handlers}
        className="group relative flex h-full flex-col overflow-hidden rounded-2xl border border-fg/[0.07] bg-surface p-4 shadow-card transition duration-300 hover:-translate-y-0.5 hover:border-copper-500/30 hover:shadow-lift sm:p-5"
      >
        {layer}
        <div className="relative flex items-start justify-between gap-3">
          <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl ring-1 ring-inset ring-fg/[0.06]", tone)}>{icon}</span>
          <ArrowUpRight className="h-4 w-4 text-steel-400 opacity-0 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-copper-400 group-hover:opacity-100" />
        </div>
        <p className="relative mt-4 text-[13px] leading-snug text-muted">{t(label)}</p>
        <p className="relative mt-0.5 font-display text-[28px] leading-tight font-bold tracking-[-0.03em] text-ink tabular-nums sm:text-[32px]">
          <CountUpText text={value} />
        </p>
        <p className={cn("relative mt-1 text-[13px] font-medium", footTone)}>{foot}</p>
      </Link>
    </StaggerItem>
  );
}

function OpsCard({ icon, tone, label, value, foot, footTone, href }: {
  icon: ReactNode; tone: string; label: string; value: string; foot: string; footTone: string; href: string;
}) {
  const { t } = useI18n();
  return (
    <StaggerItem>
      <Link
        href={href}
        className="group flex h-full items-center gap-4 rounded-2xl border border-fg/[0.07] bg-surface/70 p-4 transition duration-300 hover:border-copper-500/30 hover:bg-surface sm:px-5"
      >
        <span className={cn("grid h-12 w-12 shrink-0 place-items-center rounded-2xl ring-1 ring-inset ring-fg/[0.06] max-sm:h-11 max-sm:w-11", tone)}>{icon}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-snug text-muted">{t(label)}</p>
          <p className="font-display text-[26px] leading-tight font-bold tracking-[-0.03em] tabular-nums max-sm:text-2xl"><CountUpText text={value} /></p>
        </div>
        <span className={cn("shrink-0 rounded-full bg-fg/[0.04] px-2.5 py-1 text-right text-xs font-semibold", footTone)}>{foot}</span>
      </Link>
    </StaggerItem>
  );
}

function OperationsRow() {
  const { t } = useI18n();
  const grv = useQuery({ queryKey: ["grievances", "summary"], queryFn: () => api<GrievanceSummary>("/grievances/summary") });
  const env = useQuery({ queryKey: ["environment", "summary", ""], queryFn: () => api<EnvSummary>("/environment/summary") });
  const prod = useQuery({ queryKey: ["production", "summary", ""], queryFn: () => api<ProductionSummary>("/production/summary") });
  const overdue = grv.data?.overdue ?? 0;
  const exceed = env.data?.exceedances_30d ?? 0;
  const pct = prod.data?.achievement_pct ?? null;
  return (
    <Stagger className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-3" step={0.07}>
      <OpsCard href="/grievances" icon={<MessageSquareText className="h-5 w-5" />} tone="bg-copper-500/12 text-copper-300" label="Open grievances"
        value={grv.data ? fmtNumber(grv.data.open) : "—"}
        foot={grv.data ? `${overdue} ${t("overdue")}` : ""} footTone={overdue ? "text-bad" : "text-ok"} />
      <OpsCard href="/environment" icon={<Leaf className="h-5 w-5" />} tone="bg-bad-soft text-bad" label="Environment exceedances (30 days)"
        value={env.data ? fmtNumber(exceed) : "—"}
        foot={env.data?.compliance_pct != null ? `${env.data.compliance_pct}% ${t("within limit")}` : ""}
        footTone={exceed ? "text-bad" : "text-ok"} />
      <OpsCard href="/production" icon={<Factory className="h-5 w-5" />} tone="bg-copper-500/12 text-copper-300" label="Target achievement (FY)"
        value={pct != null ? `${pct}%` : "—"}
        foot={prod.data ? `${fmtNumber(prod.data.ytd_produced_t / 1e6, 2)} Mt` : ""}
        footTone={pct != null && pct < 90 ? "text-warn" : "text-ok"} />
    </Stagger>
  );
}

// ------------------------------------------------------------- card chrome
function Panel({ title, subtitle, link, children, className }: {
  title: ReactNode; subtitle?: string; link?: { href: string; label: string }; children: ReactNode; className?: string;
}) {
  const { t } = useI18n();
  return (
    <section className={cn("flex h-full min-w-0 flex-col rounded-[22px] border border-fg/[0.07] bg-surface bg-[linear-gradient(180deg,rgb(255_255_255/0.025),transparent_140px)] shadow-card", className)}>
      <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
        <div className="min-w-0">
          <h2 className="text-base font-bold tracking-tight text-ink">{typeof title === "string" ? t(title) : title}</h2>
          {subtitle && <p className="mt-0.5 text-[13px] text-muted">{t(subtitle)}</p>}
        </div>
        {link && (
          <Link href={link.href} className="group flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[13px] font-semibold text-copper-400 transition hover:bg-copper-500/10 hover:text-copper-300">
            {t(link.label)} <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

// ------------------------------------------------------------- sections
const DONUT = { compliant: "#34c77b", progress: "#f2b134", non: "#f25f4c" };

function ComplianceOverview({ data }: { data: DashboardSummary["compliance"] }) {
  const { t } = useI18n();
  const slices = [
    { name: "Compliant", value: data.overview.compliant, color: DONUT.compliant, bar: "bg-ok" },
    { name: "In Progress", value: data.overview.in_progress, color: DONUT.progress, bar: "bg-warn" },
    { name: "Non-Compliant", value: data.overview.non_compliant, color: DONUT.non, bar: "bg-bad" },
  ];
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <Panel title="Compliance Overview" link={{ href: "/compliance", label: "View Details" }}>
      <div className="flex flex-1 flex-col items-center gap-6 px-5 pb-6 sm:flex-row xl:flex-col 2xl:flex-row">
        <div className="relative h-48 w-48 shrink-0">
          <div aria-hidden className="absolute inset-6 rounded-full bg-ok/10 blur-2xl" />
          <ResponsiveContainer>
            <PieChart>
              <Pie data={slices} dataKey="value" innerRadius={70} outerRadius={90} paddingAngle={2} cornerRadius={6} startAngle={90} endAngle={-270} stroke="none" animationDuration={900} animationEasing="ease-out">
                {slices.map((s) => <Cell key={s.name} fill={s.color} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
            <div>
              <p className="font-display text-[38px] leading-none font-bold tracking-[-0.04em]"><CountUp value={Math.round(data.compliance_rate)} suffix="%" /></p>
              <p className="mt-1 text-[13px] text-muted">{t("Overall")}</p>
            </div>
          </div>
        </div>
        <ul className="w-full space-y-3.5 text-sm">
          {slices.map((s) => (
            <li key={s.name}>
              <div className="flex items-center gap-2.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color, boxShadow: `0 0 10px ${s.color}` }} />
                <span className="flex-1 text-steel-600">{t(s.name)}</span>
                <span className="font-display font-bold tabular-nums">{s.value}</span>
              </div>
              <GrowBar pct={(s.value / total) * 100} className="mt-1.5 h-1" barClassName={s.bar} />
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}

const OUTCOME_ICON: Record<string, string> = {
  compliant: "bg-ok-soft text-ok",
  minor_issues: "bg-warn-soft text-warn",
  non_compliant: "bg-bad-soft text-bad",
  pending: "bg-fg/5 text-steel-500",
};

function RecentInspections({ items }: { items: DashboardSummary["recent_inspections"] }) {
  const { t } = useI18n();
  return (
    <Panel title="Recent Inspections" link={{ href: "/inspections", label: "View All" }}>
      {items.length === 0 && <p className="px-5 py-8 text-center text-sm text-muted">{t("No inspections yet.")}</p>}
      <AnimatedList className="space-y-1 px-3 pb-3">
        {items.slice(0, 5).map((i) => (
          <Link key={i.id} href={`/inspections/${i.id}`} className="group flex items-center gap-3 rounded-xl px-2 py-2.5 transition hover:bg-fg/[0.03]">
            <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl", OUTCOME_ICON[i.outcome])}>
              <ClipboardList className="h-[18px] w-[18px]" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-ink">{i.mine_name}</span>
              <span className="block truncate text-xs text-muted">
                {t(`${humanize(i.inspection_type)} Inspection`)} · {fmtDate(i.inspected_at, "MMM d")}
              </span>
            </span>
            <Badge tone={outcomeTone[i.outcome]}>{outcomeLabel[i.outcome]}</Badge>
          </Link>
        ))}
      </AnimatedList>
    </Panel>
  );
}

function MineLocations({ data, focusId }: { data: DashboardSummary["mine_locations"]; focusId: string | null }) {
  const { t } = useI18n();
  return (
    <Panel title="Mine Locations" link={{ href: "/map", label: "View Map" }}>
      <div className="relative mx-3 min-h-64 flex-1 overflow-hidden rounded-2xl border border-fg/[0.06]">
        <MineMap mines={data} focusId={focusId} interactive={false} />
        <div className="glass pointer-events-none absolute bottom-3 left-3 z-[400] flex flex-wrap gap-x-4 gap-y-1 rounded-xl px-3 py-2 text-xs">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-ok shadow-[0_0_6px_#34c77b]" /> {t("Compliant")}</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-warn shadow-[0_0_6px_#f2b134]" /> {t("Minor Issues")}</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-bad shadow-[0_0_6px_#f25f4c]" /> {t("Non-Compliant")}</span>
        </div>
      </div>
      <div className="h-3" />
    </Panel>
  );
}

function UpcomingDeadlines({ items }: { items: DashboardSummary["upcoming_deadlines"] }) {
  const { t } = useI18n();
  const status = (d: number): { label: string; cls: string } =>
    d < 0 ? { label: `${t("Overdue")} ${-d}d`, cls: "bg-bad-soft text-bad" }
      : d === 0 ? { label: t("Due today"), cls: "bg-bad-soft text-bad" }
        : d <= 21 ? { label: t("Due in {n} days", { n: d }), cls: "bg-warn-soft text-warn" }
          : { label: t("Scheduled"), cls: "bg-info-soft text-info" };
  return (
    <Panel title="Upcoming Deadlines" link={{ href: "/compliance", label: "View All" }}>
      {items.length === 0 ? (
        <p className="px-5 pb-8 text-center text-sm text-muted">{t("Nothing due.")}</p>
      ) : (
        <div className="px-3 pb-3">
          <AnimatedList className="space-y-1">
            {items.slice(0, 5).map((d) => {
              const s = status(d.days_left);
              return (
                <Link
                  key={d.id}
                  href={`/compliance?item=${d.id}`}
                  className="flex items-center gap-3 rounded-xl px-2 py-2.5 transition hover:bg-fg/[0.03] sm:grid sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_7rem]"
                >
                  <span className="flex min-w-0 flex-1 items-center gap-3">
                    {/* date tile */}
                    <span className={cn("grid h-11 w-11 shrink-0 place-items-center rounded-xl text-center leading-none ring-1 ring-inset ring-fg/[0.06]", d.days_left <= 7 ? "bg-bad-soft text-bad" : "bg-fg/[0.04] text-ink")}>
                      <span>
                        <span className="block font-display text-base font-bold">{fmtDate(d.due_date, "dd")}</span>
                        <span className="block text-[9px] font-semibold uppercase opacity-70">{fmtDate(d.due_date, "MMM")}</span>
                      </span>
                    </span>
                    <span className="min-w-0 text-sm leading-snug">
                      <span className="line-clamp-2 font-medium text-ink">{d.title}</span>
                      <span className="block truncate text-xs text-muted sm:hidden">{d.mine_name}</span>
                    </span>
                  </span>
                  <span className="hidden truncate text-[13px] text-muted sm:block">{d.mine_name}</span>
                  <span className={cn("w-[7rem] shrink-0 rounded-full px-2 py-1 text-center text-xs font-semibold", s.cls)}>{s.label}</span>
                </Link>
              );
            })}
          </AnimatedList>
        </div>
      )}
    </Panel>
  );
}

function ViolationTrends({ data }: { data: DashboardSummary["violation_trends"] }) {
  const { t } = useI18n();
  const rows = data.map((m) => ({
    label: m.label,
    [t("Critical")]: m.critical,
    [t("Major")]: m.major ?? 0,
    [t("Minor")]: m.minor ?? Math.max(m.total - m.critical, 0),
    [t("Total")]: m.total,
  }));
  return (
    <Panel title="Violation Trends" subtitle="Last 6 months" link={{ href: "/reports?tab=trends", label: "Analytics" }}>
      <div className="h-72 flex-1 px-2 pb-3">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 8, right: 16, left: -14, bottom: 0 }} barCategoryGap="34%">
            <defs>
              <linearGradient id="bar-critical" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ff7a68" /><stop offset="100%" stopColor="#d9442f" /></linearGradient>
              <linearGradient id="bar-major" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f7a45a" /><stop offset="100%" stopColor="#d97a2b" /></linearGradient>
              <linearGradient id="bar-minor" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fbd89a" /><stop offset="100%" stopColor="#e3b56a" /></linearGradient>
            </defs>
            <CartesianGrid vertical={false} strokeDasharray="3 6" />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
            <Tooltip cursor={{ fill: "rgb(255 255 255 / 0.03)" }} />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey={t("Critical")} stackId="v" fill="url(#bar-critical)" animationDuration={700} />
            <Bar dataKey={t("Major")} stackId="v" fill="url(#bar-major)" animationDuration={700} />
            <Bar dataKey={t("Minor")} stackId="v" fill="url(#bar-minor)" animationDuration={700} radius={[5, 5, 0, 0]} />
            <Line type="monotone" dataKey={t("Total")} stroke="#e3a473" strokeWidth={2} dot={{ r: 3, fill: "var(--color-canvas)", stroke: "#e3a473", strokeWidth: 2 }} activeDot={{ r: 5 }} animationDuration={700} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

const PROMPTS = [
  { icon: FileText, label: "Summarize this month's inspection report",
    q: "Summarise this month's inspection findings for my mines and highlight the main hazards." },
  { icon: Search, label: "Show mines with repeated violations",
    q: "Which mines have repeated violations of the same kind in the last 6 months, and what were they?" },
  { icon: ClipboardList, label: "Draft a compliance reminder for contractors",
    q: "Draft a short compliance reminder for contractors about their overdue obligations and PPE rules." },
  { icon: ChartSpline, label: "Analyze environmental trends",
    q: "Analyse the environmental readings of the last 90 days: which parameters and mines exceed limits most often?" },
];

function AssistantCard() {
  const { t } = useI18n();
  return (
    <section className="relative flex h-full flex-col overflow-hidden rounded-[22px] border border-copper-500/25 bg-surface shadow-card">
      <div aria-hidden className="absolute -top-16 -right-16 h-48 w-48 rounded-full bg-copper-500/25 blur-3xl" />
      <div className="relative flex items-center gap-3 px-5 pt-5 pb-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-b from-copper-500 to-copper-700 text-white shadow-[0_8px_20px_-8px_rgb(212_136_78/0.9)]">
          <Sparkles className="h-5 w-5" />
        </span>
        <div>
          <h2 className="text-base font-bold tracking-tight text-ink">{t("AI Assistant")}</h2>
          <p className="text-[13px] text-muted"><Shiny text={t("Ask anything about your mines")} /></p>
        </div>
      </div>
      <div className="relative space-y-2 px-5 pb-5">
        {PROMPTS.map(({ icon: Icon, label, q }) => (
          <Link
            key={label}
            href={`/assistant?q=${encodeURIComponent(q)}`}
            className="group flex min-h-12 w-full items-center gap-3 rounded-xl border border-fg/[0.07] bg-fg/[0.02] px-3.5 py-2.5 text-sm text-steel-600 transition hover:border-copper-500/35 hover:bg-copper-500/[0.07] hover:text-ink"
          >
            <Icon className="h-4 w-4 shrink-0 text-copper-400" />
            <span className="flex-1">{t(label)}</span>
            <ArrowRight className="h-4 w-4 text-steel-400 transition group-hover:translate-x-0.5 group-hover:text-copper-400" />
          </Link>
        ))}
      </div>
    </section>
  );
}

function HighRiskList({ items }: { items: DashboardSummary["high_risk_mines"] }) {
  return (
    <ul className="grid grid-cols-1 gap-3 px-5 pb-5 sm:grid-cols-2 xl:grid-cols-5">
      {items.map((m) => {
        const score = m.risk_score ?? 0;
        const tone = score >= 60 ? "bg-bad" : score >= 35 ? "bg-warn" : "bg-ok";
        return (
          <li key={m.id} className="rounded-2xl border border-fg/[0.07] bg-fg/[0.02] p-4 transition hover:border-fg/15">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">{m.name}</p>
                <p className="text-xs text-muted">{m.code}</p>
              </div>
              <p className="font-display text-xl font-bold tabular-nums">{m.risk_score?.toFixed(0) ?? "—"}</p>
            </div>
            <GrowBar pct={score} className="mt-3 h-1.5" barClassName={tone} />
          </li>
        );
      })}
    </ul>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading dashboard…">
      <div className="shimmer h-44 rounded-[28px]" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => <div key={i} className="shimmer h-36 rounded-2xl" />)}
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="shimmer h-80 rounded-[22px] xl:col-span-4" />
        <div className="shimmer h-80 rounded-[22px] xl:col-span-8" />
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- page
export default function DashboardPage() {
  const { me, can } = useSession();
  const { t } = useI18n();
  const [period, setPeriod] = useState<PeriodKey>("this_month");
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardSummary>("/dashboard/summary"),
    refetchInterval: 60_000,
  });
  if (isLoading) return <DashboardSkeleton />;
  if (error || !data) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const k = data.kpis;
  const myMine = me.mine_id ? data.mine_locations.find((m) => m.id === me.mine_id) : undefined;
  const coords = myMine ? { lat: myMine.latitude, lon: myMine.longitude } : data.mine_locations[0] ? { lat: data.mine_locations[0].latitude, lon: data.mine_locations[0].longitude } : null;
  const [from, to] = periodRange(period);
  const reportHref = `/reports?new=1&start=${iso(from)}&end=${iso(to)}`;
  const change = k.inspections_change_pct;

  return (
    <div className="space-y-4">
      <HeroBand name={me.full_name} scope={me.mine?.name ?? me.subsidiary_name} coords={coords} rate={k.compliance_rate}>
        <PeriodPicker value={period} onChange={setPeriod} />
        {can("report:generate") && (
          <Link
            href={reportHref}
            className="group inline-flex h-11 items-center gap-2 rounded-xl bg-gradient-to-b from-copper-500 to-copper-600 px-5 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_10px_28px_-10px_rgb(212_136_78/0.9)] transition hover:-translate-y-px hover:brightness-110"
          >
            <FileText className="h-4 w-4" aria-hidden />
            {t("Generate Report")}
          </Link>
        )}
      </HeroBand>

      {/* KPI row */}
      <Stagger className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-5">
        <Kpi href="/map" icon={<ClipboardList className="h-5 w-5" />} tone="bg-ok-soft text-ok" label="Total Mines"
          value={fmtNumber(k.total_mines)} foot={k.new_mines_this_month ? `+${k.new_mines_this_month} ${t("this month")}` : t("All onboarded")} />
        <Kpi href="/compliance" icon={<CalendarDays className="h-5 w-5" />} tone="bg-info-soft text-info" label="Compliance Items"
          value={fmtNumber(k.compliance_items)} foot={`${Math.round(k.compliance_rate)}% ${t("on track")}`} />
        <Kpi href="/violations?open_only=true" icon={<TriangleAlert className="h-5 w-5" />} tone="bg-bad-soft text-bad" label="Open Violations"
          value={fmtNumber(k.open_violations)} foot={`${k.critical_violations} ${t("critical")}`} footTone={k.critical_violations ? "text-bad" : "text-ok"} />
        <Kpi href="/contractors" icon={<Users className="h-5 w-5" />} tone="bg-violet-soft text-violet" label="Active Contractors"
          value={fmtNumber(k.active_contractors)}
          foot={k.verified_contractors === k.active_contractors ? t("All verified") : `${k.verified_contractors} ${t("verified")}`}
          footTone={k.verified_contractors === k.active_contractors ? "text-ok" : "text-warn"} />
        <Kpi href="/inspections" icon={<Search className="h-5 w-5" />} tone="bg-copper-500/12 text-copper-300" label="Inspections (This Month)"
          value={fmtNumber(k.inspections_this_month)}
          foot={change === null ? `${fmtNumber(k.inspections)} ${t("in total")}` : `${change >= 0 ? "+" : ""}${change}% ${t("this month")}`}
          footTone={change !== null && change < 0 ? "text-bad" : "text-ok"} className="max-md:col-span-2" />
      </Stagger>

      <OperationsRow />

      {k.open_anomalies > 0 && (
        <Link href="/reports?tab=anomalies" className="group flex items-center gap-3 rounded-2xl border border-warn/25 bg-warn-soft px-5 py-3.5 text-sm font-medium text-warn transition hover:border-warn/45">
          <HardHat className="h-5 w-5 shrink-0" /> {t("{n} unusual patterns need a look", { n: k.open_anomalies })}
          <ArrowRight className="ml-auto h-4 w-4 shrink-0 transition group-hover:translate-x-1" />
        </Link>
      )}

      {/* bento */}
      <Stagger className="grid grid-cols-1 gap-4 xl:grid-cols-12" step={0.08}>
        <StaggerItem className="xl:col-span-4"><ComplianceOverview data={data.compliance} /></StaggerItem>
        <StaggerItem className="xl:col-span-8"><ViolationTrends data={data.violation_trends} /></StaggerItem>
        <StaggerItem className="xl:col-span-5"><RecentInspections items={data.recent_inspections} /></StaggerItem>
        <StaggerItem className="xl:col-span-7"><MineLocations data={data.mine_locations} focusId={me.mine_id} /></StaggerItem>
        <StaggerItem className={can("ai:use") ? "xl:col-span-7" : "xl:col-span-12"}><UpcomingDeadlines items={data.upcoming_deadlines} /></StaggerItem>
        {can("ai:use") && <StaggerItem className="xl:col-span-5"><AssistantCard /></StaggerItem>}
      </Stagger>

      {data.high_risk_mines.length > 0 && (
        <Panel title="High-risk mines" subtitle="Mines most likely to have a serious violation soon" link={can("ai:use") ? { href: "/reports?tab=risk", label: "Risk analytics" } : undefined}>
          <HighRiskList items={data.high_risk_mines} />
        </Panel>
      )}
    </div>
  );
}
