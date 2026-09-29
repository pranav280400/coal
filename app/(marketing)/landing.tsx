"use client";

import {
  ArrowLeftRight,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  ChevronRight,
  Droplets,
  Link2,
  Wind,
  Bot,
  Building2,
  ClipboardCheck,
  Factory,
  FileText,
  HardHat,
  Landmark,
  Languages,
  MapPin,
  MessageSquareWarning,
  ServerCog,
  ShieldCheck,
  TriangleAlert,
  Truck,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import { motion, useScroll, useTransform } from "motion/react";
import Link from "next/link";
import { useRef, useState, type ReactNode } from "react";
import { Logo, MinistryMark } from "@/components/brand";
import { Backdrop, CopperText, Decrypt, GlowCard, Marquee, Reveal, Split, StarLink, Typing } from "@/components/fx";
import { FadeContent, Stagger, StaggerItem, useSpotlight } from "@/components/motion";
import { cn } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import { Hero, ImpactBand, STEPS, Tour } from "./hero";
import { SiteNav } from "./site-nav";

// ---------------------------------------------------------------- content
const STATUTES = [
  "Mines Act, 1952",
  "Coal Mines Regulations, 2017",
  "Environment (Protection) Act, 1986",
  "Air Act, 1981",
  "Water Act, 1974",
  "Contract Labour Act, 1970",
  "MMDR Act, 1957",
  "Mines Rules, 1955",
];


type Feature = { icon: LucideIcon; title: string; body: string };

const FEATURES: Feature[] = [
  { icon: ClipboardCheck, title: "Statutory Compliance", body: "Every safety, environment, production and labour obligation tracked per mine, with reminders at 7, 3 and 1 days and automatic escalation once overdue." },
  { icon: MapPin, title: "Geo-tagged Inspections", body: "Field officers capture inspections with GPS, timestamp and photo evidence. Works fully offline and syncs the moment a signal returns." },
  { icon: TriangleAlert, title: "Violation to Closure", body: "Flag, assign, evidence and independently verify. Missed deadlines are escalated automatically, step by step, so nothing is quietly forgotten." },
  { icon: FileText, title: "Reports & Digitisation", body: "Scheduled statutory reports as PDF and Excel, and OCR that turns legacy paper records into structured, searchable data." },
  { icon: ShieldCheck, title: "Tamper-evident Audit", body: "Every change is recorded permanently. Any attempt to alter the history is detected." },
  { icon: MessageSquareWarning, title: "Grievance Redressal", body: "Workers and contractors raise grievances — anonymously if they choose. Each gets an owner and a deadline, escalates if missed, and is closed only when the person who raised it confirms." },
  { icon: Factory, title: "Production & Environment", body: "Monthly production and despatch returns against target, plus air, noise and effluent readings checked against statutory limits. A breach opens a violation automatically." },
  { icon: Languages, title: "Hindi & English", body: "Switch the whole interface between Hindi and English, and ask the assistant or digitise documents in either language." },
];

/** Product facts for the heading strip — counts of what exists, not claims. */
const FACTS = [
  { value: "8", label: "Integrated modules" },
  { value: "5", label: "Role-based views" },
  { value: "2", label: "Languages" },
  { value: "24/7", label: "Automated monitoring" },
];

const ASK = [
  "Which mines have overdue safety obligations this week?",
  "What does CMR 2017 require for ventilation surveys?",
  "Summarise last month's inspection findings for Jharia.",
  "Draft a reminder to contractors about PPE compliance.",
];


const ROLES: { icon: LucideIcon; role: string; body: string }[] = [
  { icon: HardHat, role: "Mine Official", body: "Runs day-to-day compliance for a mine: records inspections, closes violations with evidence and files monthly returns." },
  { icon: Building2, role: "Corporate Management", body: "Sees every mine in the subsidiary on one screen: risk, overdue work and trends, with reports ready to send." },
  { icon: Landmark, role: "Regulator", body: "Inspects, flags violations and verifies closures independently — with the full history behind each decision." },
  { icon: Truck, role: "Contractor", body: "Keeps licences, workforce and obligations current, and answers the actions assigned to them on time." },
];

const PRINCIPLES: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: Building2, title: "Multi-tenant by design", body: "Every mine, subsidiary and contractor sees only its own data." },
  { icon: WifiOff, title: "Offline-first in the field", body: "Reports saved offline are sent when the signal returns — nothing is lost or duplicated." },
  { icon: Bot, title: "Explainable AI", body: "Every risk score shows the reasons behind it." },
  { icon: ServerCog, title: "Runs on your infrastructure", body: "Runs on government servers, with no data leaving the network." },
];

// ------------------------------------------------------------------ bits
function Eyebrow({ children }: { children: string }) {
  const { t } = useI18n();
  return (
    <p className="inline-flex items-center gap-2 text-xs font-semibold tracking-[0.18em] text-copper-400 uppercase">
      <span className="h-px w-6 bg-copper-500/70" />
      {t(children)}
    </p>
  );
}

function SectionTitle({ eyebrow, title, accent, body, center }: { eyebrow: string; title: string; accent?: string; body?: string; center?: boolean }) {
  const { t } = useI18n();
  return (
    <div className={cn("max-w-3xl", center && "mx-auto text-center")}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-4 text-[clamp(2rem,4.4vw,3.5rem)] leading-[1.02] font-bold tracking-[-0.035em] text-ink">
        <Split text={t(title)} by="words" delay={40} />
        {accent && (
          <>
            {" "}
            <CopperText>{t(accent)}</CopperText>
          </>
        )}
      </h2>
      {body && (
        <FadeContent delay={0.15}>
          <p className={cn("mt-5 text-lg leading-relaxed text-muted", center && "mx-auto max-w-2xl")}>{t(body)}</p>
        </FadeContent>
      )}
    </div>
  );
}

// ------------------------------------------------------ statutes + stats
function Statutes() {
  const { t } = useI18n();
  return (
    <section aria-label={t("Regulations tracked")} className="relative border-y border-fg/[0.06] bg-surface/40 py-6">
      <p className="mb-4 text-center text-[11px] font-semibold tracking-[0.2em] text-steel-500 uppercase">{t("Obligations tracked under")}</p>
      <div className="[mask-image:linear-gradient(90deg,transparent,black_12%,black_88%,transparent)]">
        <Marquee
          velocity={28}
          className="font-display text-xl font-semibold tracking-tight text-steel-600 sm:text-2xl"
          items={[
            <span key="s" className="inline-flex items-center">
              {STATUTES.map((s) => (
                <span key={s} className="inline-flex items-center">
                  <span className="px-7">{s}</span>
                  <span className="h-1.5 w-1.5 rotate-45 bg-copper-500/70" />
                </span>
              ))}
            </span>,
          ]}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- bento
function Platform() {
  const { t } = useI18n();
  const [compliance, inspections, violations, reports, audit, grievance, production, hindi] = FEATURES;
  return (
    <section id="features" className="relative mx-auto max-w-[1500px] px-5 sm:px-8 lg:px-14 scroll-mt-28 pt-16 pb-16 lg:pt-20 lg:pb-24">
      <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
        <SectionTitle
          eyebrow="Platform"
          title="One platform for the whole"
          accent="compliance lifecycle."
          body="From the first field observation to verified closure — every obligation, owner and deadline in one system of record."
        />
        <FadeContent delay={0.1} className="shrink-0">
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-fg/[0.08] bg-fg/[0.08] sm:grid-cols-4">
            {FACTS.map((f) => (
              <div key={f.label} className="bg-surface px-5 py-4 lg:px-6">
                <dt className="sr-only">{t(f.label)}</dt>
                <dd className="font-display text-3xl leading-none font-bold tracking-[-0.03em] text-ink">{f.value}</dd>
                <dd className="mt-1.5 text-xs leading-tight whitespace-nowrap text-muted">{t(f.label)}</dd>
              </div>
            ))}
          </dl>
        </FadeContent>
      </div>

      <Stagger className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-6 lg:mt-12 lg:grid-cols-12" step={0.06}>
        {/* AI assistant — the wide lead tile */}
        {/* row 1: assistant (wide) · inspections · statutory compliance */}
        <StaggerItem className="md:col-span-6">
          <GlowCard className="h-full">
            <div className="flex h-full flex-col gap-6 p-7 sm:p-8 xl:flex-row xl:items-end">
              <div className="flex-1">
                <FeatureIcon icon={Bot} />
                <h3 className="mt-6 text-2xl font-bold tracking-tight text-ink">{t("AI Compliance Assistant")}</h3>
                <p className="mt-3 max-w-md leading-relaxed text-muted">
                  {t("Ask a question in plain language and get an answer grounded in the actual statute, with citations back to the regulation it came from.")}
                </p>
                <Chips items={["Cites the statute", "Hindi & English", "PDF & photo uploads", "Runs on-premise"]} className="mt-5" />
              </div>
              <div className="w-full rounded-2xl border border-fg/[0.08] bg-canvas/80 p-4 xl:max-w-[300px]">
                <p className="text-[11px] font-semibold tracking-[0.14em] text-steel-500 uppercase">{t("Ask Lumen")}</p>
                <p className="mt-3 min-h-[3.2em] text-[15px] leading-snug text-ink">
                  <Typing texts={ASK.map((q) => t(q))} />
                </p>
                <div className="mt-4 flex items-center gap-2 text-xs text-muted">
                  <span className="rounded-md bg-copper-500/12 px-2 py-0.5 font-medium text-copper-300">CMR 2017</span>
                  <span className="rounded-md bg-fg/5 px-2 py-0.5">{t("Cited")}</span>
                </div>
              </div>
            </div>
          </GlowCard>
        </StaggerItem>

        {/* inspections with a stylised map of pins */}
        <StaggerItem className="md:col-span-3">
          <GlowCard className="h-full">
            <div className="relative flex h-full flex-col overflow-hidden p-7">
              <PinField />
              <div className="relative mt-auto pt-24">
                <FeatureIcon icon={inspections.icon} />
                <h3 className="mt-5 text-xl font-bold tracking-tight text-ink">{t(inspections.title)}</h3>
                <p className="mt-2.5 text-[15px] leading-relaxed text-muted">{t(inspections.body)}</p>
                <Chips items={["GPS", "Photo evidence", "Offline sync"]} className="mt-4" />
              </div>
            </div>
          </GlowCard>
        </StaggerItem>

        <StaggerItem className="md:col-span-3">
          <FeatureTile feature={compliance} extra={<ReminderTrack />} />
        </StaggerItem>

        {/* row 2: four equal tiles */}
        <StaggerItem className="md:col-span-3">
          <FeatureTile feature={violations} extra={<ClosureTrack />} />
        </StaggerItem>
        <StaggerItem className="md:col-span-3">
          <FeatureTile feature={reports} extra={<Chips items={["PDF", "Excel", "OCR", "Scheduled"]} />} />
        </StaggerItem>
        <StaggerItem className="md:col-span-3">
          <FeatureTile feature={audit} extra={<HashChain />} />
        </StaggerItem>
        <StaggerItem className="md:col-span-3">
          <FeatureTile feature={grievance} extra={<Chips items={["Anonymous option", "Owner + deadline", "Closed by complainant"]} />} />
        </StaggerItem>

        {/* row 3: two tiles and the call to action */}
        <StaggerItem className="md:col-span-2 lg:col-span-4">
          <FeatureTile feature={production} extra={<ReadingsRow />} />
        </StaggerItem>
        <StaggerItem className="md:col-span-2 lg:col-span-4">
          <FeatureTile feature={hindi} extra={<LangSwap />} />
        </StaggerItem>
        <StaggerItem className="md:col-span-2 lg:col-span-4">
          <Link href="/login" className="group flex h-full flex-col justify-between rounded-3xl bg-gradient-to-br from-copper-500 to-copper-700 p-7 text-white shadow-[0_24px_60px_-24px_rgb(212_136_78/0.8)] transition hover:brightness-110">
            <ArrowUpRight className="h-8 w-8 self-end transition group-hover:translate-x-1 group-hover:-translate-y-1" />
            <div>
              <p className="font-display text-2xl leading-tight font-bold">{t("See it with your own mine data")}</p>
              <p className="mt-2 text-sm text-white/80">{t("Sign in to open your dashboard")}</p>
            </div>
          </Link>
        </StaggerItem>
      </Stagger>
    </section>
  );
}

function FeatureIcon({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-b from-copper-500/25 to-copper-500/5 text-copper-300 ring-1 ring-copper-500/25 shadow-[0_0_30px_-6px_rgb(212_136_78/0.5)]">
      <Icon className="h-[22px] w-[22px]" strokeWidth={1.8} />
    </span>
  );
}

function FeatureTile({ feature, large, extra }: { feature: Feature; large?: boolean; extra?: ReactNode }) {
  const { t } = useI18n();
  return (
    <GlowCard className="h-full">
      <div className={cn("flex h-full flex-col p-6 sm:p-7", large && "sm:p-8")}>
        <FeatureIcon icon={feature.icon} />
        <h3 className={cn("mt-5 font-bold tracking-tight text-ink", large ? "text-2xl" : "text-xl")}>{t(feature.title)}</h3>
        <p className="mt-2.5 text-[15px] leading-relaxed text-muted">{t(feature.body)}</p>
        {extra && <div className="mt-auto pt-5">{extra}</div>}
      </div>
    </GlowCard>
  );
}

// ------------------------------------------------------- tile visuals
/** Small pills naming what a module covers. */
function Chips({ items, className }: { items: string[]; className?: string }) {
  const { t } = useI18n();
  return (
    <ul className={cn("flex flex-wrap gap-1.5", className)}>
      {items.map((i) => (
        <li key={i} className="rounded-full border border-fg/[0.08] bg-fg/[0.03] px-2.5 py-1 text-xs font-medium text-steel-600">
          {t(i)}
        </li>
      ))}
    </ul>
  );
}

/** Reminder schedule: 7 → 3 → 1 days, then escalation. */
function ReminderTrack() {
  const { t } = useI18n();
  const steps = [
    { k: "7d", l: "Reminder" },
    { k: "3d", l: "Reminder" },
    { k: "1d", l: "Final" },
    { k: "!", l: "Escalate", hot: true },
  ];
  return (
    <ol className="relative grid grid-cols-4">
      <span aria-hidden className="absolute top-3.5 right-[12.5%] left-[12.5%] h-px bg-gradient-to-r from-fg/15 via-copper-500/50 to-bad/70" />
      {steps.map((s) => (
        <li key={s.k} className="relative flex flex-col items-center gap-1.5 text-center">
          <span
            className={cn(
              "grid h-7 w-7 place-items-center rounded-full text-[11px] font-bold ring-4 ring-surface",
              s.hot ? "bg-bad text-white" : "bg-copper-500/15 text-copper-400",
            )}
          >
            {s.k}
          </span>
          <span className="text-[11px] text-muted">{t(s.l)}</span>
        </li>
      ))}
    </ol>
  );
}

/** Flag → assign → evidence → verify. */
function ClosureTrack() {
  const { t } = useI18n();
  const steps = ["Flagged", "Assigned", "Evidence", "Verified"];
  return (
    <ol className="flex items-center gap-1">
      {steps.map((s, i) => (
        <li key={s} className="flex min-w-0 flex-1 items-center gap-1">
          <span
            className={cn(
              "w-full truncate rounded-md px-1.5 py-1 text-center text-[11px] font-semibold",
              i === steps.length - 1 ? "bg-ok-soft text-ok" : "bg-fg/[0.05] text-steel-600",
            )}
          >
            {t(s)}
          </span>
          {i < steps.length - 1 && <ChevronRight className="h-3 w-3 shrink-0 text-steel-400" />}
        </li>
      ))}
    </ol>
  );
}

/** Each record seals the one before it — the idea behind the tamper-evident trail. */
function HashChain() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-1.5">
      {["a91f", "3c07", "e5d2"].map((h, i) => (
        <span key={h} className="flex items-center gap-1.5">
          <span className="rounded-md border border-fg/[0.08] bg-fg/[0.03] px-2 py-1 font-mono text-[11px] text-steel-600">#{h}…</span>
          {i < 2 && <Link2 className="h-3.5 w-3.5 text-copper-500/70" />}
        </span>
      ))}
      <span className="ml-auto inline-flex items-center gap-1 text-[11px] font-semibold text-ok">
        <ShieldCheck className="h-3.5 w-3.5" /> {t("Intact")}
      </span>
    </div>
  );
}

/** What is measured, and what a breach does. */
function ReadingsRow() {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {[
        { i: Wind, l: "Air" },
        { i: AudioLines, l: "Noise" },
        { i: Droplets, l: "Effluent" },
      ].map(({ i: Icon, l }) => (
        <span key={l} className="inline-flex items-center gap-1.5 rounded-full border border-fg/[0.08] bg-fg/[0.03] px-2.5 py-1 text-xs font-medium text-steel-600">
          <Icon className="h-3.5 w-3.5 text-copper-500" /> {t(l)}
        </span>
      ))}
      <span className="inline-flex items-center gap-1 rounded-full bg-bad-soft px-2.5 py-1 text-xs font-semibold text-bad">
        {t("Breach → violation")}
      </span>
    </div>
  );
}

/** The same label in both languages. */
function LangSwap() {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="rounded-lg border border-fg/[0.08] bg-fg/[0.03] px-3 py-1.5 font-medium text-ink">Compliance</span>
      <ArrowLeftRight className="h-4 w-4 text-copper-500" />
      <span lang="hi" className="rounded-lg border border-copper-500/25 bg-copper-500/10 px-3 py-1.5 font-medium text-copper-400">अनुपालन</span>
    </div>
  );
}

/** Abstract field of mine pins with a sweeping scan ring — decoration for the inspections tile. */
function PinField() {
  const pins = [
    [18, 22, "ok"], [42, 14, "ok"], [66, 30, "warn"], [30, 46, "ok"], [78, 12, "ok"], [54, 52, "bad"], [86, 44, "ok"], [12, 58, "warn"],
  ] as const;
  return (
    <div aria-hidden className="absolute inset-x-0 top-0 h-44 [mask-image:linear-gradient(to_bottom,black_60%,transparent)]">
      <div className="absolute inset-0 bg-[radial-gradient(var(--dot)_1px,transparent_1px)] bg-[size:14px_14px]" />
      <span className="absolute top-[40%] left-[54%] h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full border border-copper-500/30 motion-safe:animate-ping [animation-duration:3.5s]" />
      {pins.map(([x, y, tone], i) => (
        <span
          key={i}
          className={cn(
            "absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-4",
            tone === "ok" ? "bg-ok ring-ok/15" : tone === "warn" ? "bg-warn ring-warn/15" : "bg-bad ring-bad/20 shadow-[0_0_14px_#f25f4c]",
          )}
          style={{ left: `${x}%`, top: `${y + 10}%` }}
        />
      ))}
    </div>
  );
}

// ------------------------------------------------------------ workflow
function Workflow() {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 75%", "end 55%"] });
  const fill = useTransform(scrollYProgress, [0, 1], [0, 1]);
  return (
    <section id="workflow" className="relative scroll-mt-28 overflow-hidden border-t border-fg/[0.06] py-16 lg:py-24">
      <div aria-hidden className="absolute inset-0 bg-[radial-gradient(700px_300px_at_15%_0%,rgb(212_136_78/0.08),transparent_70%)]" />
      <div className="relative mx-auto max-w-[1500px] px-5 sm:px-8 lg:px-14">
        <SectionTitle eyebrow="How it works" title="From field to" accent="verified closure." />

        <div ref={ref} className="relative mt-12">
          {/* progress rail */}
          <div aria-hidden className="absolute top-6 right-0 left-0 hidden h-px bg-fg/[0.08] lg:block">
            <motion.div style={{ scaleX: fill }} className="h-px origin-left bg-gradient-to-r from-copper-600 via-copper-400 to-copper-300 shadow-[0_0_12px_#e3a473]" />
          </div>
          <ol className="grid grid-cols-1 gap-10 lg:grid-cols-4 lg:gap-8">
            {STEPS.map((s, i) => (
              <FadeContent as="li" key={s.code} delay={i * 0.1} className="relative">
                <span className="relative z-10 grid h-12 w-12 place-items-center rounded-2xl border border-fg/10 bg-raised text-copper-300 shadow-[0_0_0_6px_var(--color-canvas)]">
                  <s.icon className="h-5 w-5" />
                </span>
                <p className="mt-6 font-mono text-xs tracking-[0.2em] text-copper-400">
                  <Decrypt text={`STEP ${s.code}`} />
                </p>
                <h3 className="mt-2 text-2xl font-bold tracking-tight text-ink">{t(s.title)}</h3>
                <p className="mt-3 leading-relaxed text-muted">{t(s.body)}</p>
              </FadeContent>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------ statement
function Statement() {
  const { t } = useI18n();
  return (
    <section id="about" className="mx-auto grid grid-cols-1 max-w-[1500px] px-5 sm:px-8 lg:px-14 scroll-mt-28 gap-10 border-t border-fg/[0.06] py-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16 lg:py-24">
      <div className="lg:order-2">
        <Eyebrow>About Lumen</Eyebrow>
        <Reveal
          className="!my-5"
          textClassName="!font-display !text-[clamp(1.45rem,2.3vw,2.25rem)] !leading-[1.3] !font-semibold !tracking-[-0.02em] text-ink"
        >
          {t("Coal governance spans subsidiaries, mine sites, contractors and regulators — today largely joined by spreadsheets and paper. Lumen replaces that with a single system of record: field activity flows in as events, workflows chase deadlines on their own, and every change leaves a trace that cannot be quietly rewritten.")}
        </Reveal>
      </div>
      <Stagger className="grid grid-cols-1 content-start gap-px self-center overflow-hidden rounded-3xl border border-fg/[0.07] bg-fg/[0.07] sm:grid-cols-2 lg:order-1" step={0.07}>
        {PRINCIPLES.map((p) => (
          <StaggerItem key={p.title} className="h-full">
            <div className="h-full bg-canvas p-6">
              <p.icon className="h-5 w-5 text-copper-400" />
              <p className="mt-4 font-semibold text-ink">{t(p.title)}</p>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{t(p.body)}</p>
            </div>
          </StaggerItem>
        ))}
      </Stagger>
    </section>
  );
}

// ---------------------------------------------------------------- roles
function Roles() {
  const { t } = useI18n();
  return (
    <section id="roles" className="relative scroll-mt-28 border-t border-fg/[0.06] py-16 lg:py-24">
      <div className="mx-auto max-w-[1500px] px-5 sm:px-8 lg:px-14">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <SectionTitle eyebrow="Who it's for" title="One record," accent="every desk." />
          <FadeContent delay={0.1} className="max-w-sm text-muted lg:pb-2">
            {t("Each role sees exactly what it is responsible for — and nothing it is not.")}
          </FadeContent>
        </div>
        <Stagger className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:mt-12 lg:grid-cols-4" step={0.08}>
          {ROLES.map((r, i) => (
            <StaggerItem key={r.role} className="h-full">
              <RoleCard {...r} index={i} />
            </StaggerItem>
          ))}
        </Stagger>
      </div>
    </section>
  );
}

function RoleCard({ icon: Icon, role, body, index }: { icon: LucideIcon; role: string; body: string; index: number }) {
  const { t } = useI18n();
  const { handlers, layer } = useSpotlight("rgba(212, 136, 78, 0.14)");
  return (
    <article
      {...handlers}
      className="group relative flex h-full flex-col overflow-hidden rounded-3xl border border-fg/[0.07] bg-surface/70 p-7 transition duration-300 hover:-translate-y-1 hover:border-copper-500/30"
    >
      {layer}
      <div className="relative flex items-center justify-between">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-fg/[0.05] text-ink ring-1 ring-fg/10 transition group-hover:bg-copper-500/15 group-hover:text-copper-300">
          <Icon className="h-5 w-5" />
        </span>
        <span className="font-mono text-xs text-steel-400">0{index + 1}</span>
      </div>
      <h3 className="relative mt-8 text-xl font-bold tracking-tight text-ink">{t(role)}</h3>
      <p className="relative mt-2.5 text-[15px] leading-relaxed text-muted">{t(body)}</p>
    </article>
  );
}

// ------------------------------------------------------------------ CTA
function Contact() {
  const { t } = useI18n();
  return (
    <section id="contact" className="scroll-mt-28 px-3 pb-3 sm:px-5 sm:pb-5">
      <div className="grain relative isolate mx-auto max-w-[1500px] overflow-hidden rounded-[2.5rem] border border-fg/[0.08] bg-surface">
        <Backdrop kind="threads" className="-z-10" />
        <div className="relative mx-auto max-w-3xl px-6 py-16 text-center sm:py-20 lg:py-24">
          <Eyebrow>Contact</Eyebrow>
          <h2 className="mt-5 text-[clamp(2.2rem,5vw,4.2rem)] leading-[1.02] font-bold tracking-[-0.04em] text-ink">
            <Split text={t("See Lumen against")} by="words" delay={50} /> <CopperText>{t("your own mine data.")}</CopperText>
          </h2>
          <FadeContent delay={0.15}>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-muted">
              {t("We will walk through compliance tracking, a live inspection, an escalation as it fires, and the audit trail behind it.")}
            </p>
          </FadeContent>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <StarLink href="/login">
              <span className="inline-flex items-center gap-2">
                {t("Request Demo")} <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
              </span>
            </StarLink>
            <Link href="/login" className="inline-flex h-[52px] items-center rounded-[20px] px-6 text-[15px] font-semibold text-muted transition hover:text-ink">
              {t("Sign In")}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  const { t } = useI18n();
  return (
    <footer className="mx-auto max-w-[1500px] px-5 sm:px-8 lg:px-14 pt-14 pb-10">
      <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
        <div className="max-w-xs">
          <Logo />
          <p className="mt-4 text-sm leading-relaxed text-muted">
            {t("AI-based smart governance and compliance monitoring for coal mines.")}
          </p>
        </div>
        <nav className="grid grid-cols-2 gap-x-14 gap-y-3 text-sm" aria-label="Footer">
          {[
            ["#platform", "Platform"],
            ["#workflow", "How it works"],
            ["#roles", "Who it's for"],
            ["#contact", "Contact"],
            ["/login", "Sign in"],
            ["/forgot-password", "Forgot Password?"],
          ].map(([href, label]) => (
            <a key={href} href={href} className="text-muted transition hover:text-ink">
              {t(label)}
            </a>
          ))}
        </nav>
        <MinistryMark />
      </div>
      <div className="hairline mt-12" />
      <p className="mt-6 text-center text-xs text-steel-500">
        {t("Ministry of Coal · Government of India — Problem Statement 26024, Smart India Hackathon 2026")}
      </p>
    </footer>
  );
}

export function Landing() {
  const [tour, setTour] = useState(false);
  return (
    <>
      <SiteNav />
      <main>
        <Hero onTour={() => setTour(true)} />
        <ImpactBand onTour={() => setTour(true)} />
        <Statutes />
        <Platform />
        <Workflow />
        <Statement />
        <Roles />
        <Contact />
      </main>
      <Footer />
      <Tour open={tour} onClose={() => setTour(false)} />
    </>
  );
}
