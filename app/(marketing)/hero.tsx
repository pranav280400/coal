"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import {
  ArrowRight,
  ArrowUpRight,
  BellRing,
  Brain,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  FileText,
  Fingerprint,
  Landmark,
  Mountain,
  Play,
  Radio,
  RadioTower,
  ScanLine,
  Sprout,
  Boxes,
  X,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Backdrop, Magnetic, Spark, Split } from "@/components/fx";
import { cn } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

gsap.registerPlugin(useGSAP, ScrollTrigger);

/*
 * Hero + impact band, built to the approved comp (public/images/landingpage.png).
 * The photo is hero-photo.webp: the comp's photo with its baked-in cards dissolved, so the
 * live cards below sit exactly where the comp put them. Card geometry is in % of the photo
 * box and type is in cqw, so the whole composition scales together at any width.
 */

export const STEPS: { icon: LucideIcon; code: string; title: string; body: string }[] = [
  { icon: ScanLine, code: "01", title: "Capture", body: "Inspections, readings, returns and grievances enter from the field — online or offline — with GPS, time and evidence attached." },
  { icon: Radio, code: "02", title: "Monitor", body: "Every record is checked against the obligation it belongs to. Limits, due dates and patterns are watched continuously." },
  { icon: BellRing, code: "03", title: "Escalate", body: "When something slips, the right owner is told — then their manager, then the regulator — automatically, on a fixed timetable." },
  { icon: Fingerprint, code: "04", title: "Prove", body: "Closure needs evidence and independent verification, and every step is written to an audit trail that cannot be quietly rewritten." },
];

const FEATURES: { icon: LucideIcon; a: string; b: string }[] = [
  { icon: RadioTower, a: "Real-time", b: "Compliance" },
  { icon: Brain, a: "AI-powered", b: "Insights" },
  { icon: Landmark, a: "Transparent", b: "Governance" },
  { icon: Boxes, a: "Sustainable", b: "Mining" },
];

const BARS = [18, 26, 22, 40, 34, 52, 46, 64, 58, 76, 70, 88];

// --------------------------------------------------------------------- hero
export function Hero({ onTour }: { onTour: () => void }) {
  const { t } = useI18n();
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const q = gsap.utils.selector(root);
        const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

        // photo wipes in from the right while it settles from a slight zoom
        tl.from(q("[data-photo-inner]"), { clipPath: "inset(0 0 0 100%)", duration: 1.5, ease: "power4.inOut" }, 0)
          .from(q("[data-photo-img]"), { scale: 1.18, duration: 2.2, ease: "power3.out" }, 0)
          // copy
          .from(q("[data-eyebrow] > span"), { opacity: 0, y: 8, stagger: 0.05, duration: 0.5 }, 0.25)
          .from(q("[data-char]"), { yPercent: 115, rotate: 8, stagger: 0.07, duration: 1.1, ease: "expo.out" }, 0.35)
          .from(q("[data-tag]"), { yPercent: 110, stagger: 0.12, duration: 1, ease: "expo.out" }, 0.7)
          .from(q("[data-fade]"), { opacity: 0, y: 18, stagger: 0.1, duration: 0.8 }, 1.0)
          .from(q("[data-feature]"), { opacity: 0, y: 16, stagger: 0.08, duration: 0.6 }, 1.2);

        // copper swoosh under the tagline, then the connector lines, drawn like a pen
        const draw = (el: Element, at: number, duration: number) => {
          const path = el as SVGPathElement;
          const len = path.getTotalLength();
          gsap.set(path, { strokeDasharray: len, strokeDashoffset: len });
          tl.to(path, { strokeDashoffset: 0, duration, ease: "power2.inOut" }, at);
        };
        q("[data-swoosh]").forEach((el) => draw(el, 1.05, 0.9));
        q("[data-draw]").forEach((el, i) => draw(el, 1.3 + i * 0.1, 0.8));
        tl.from(q("[data-dot]"), { scale: 0, duration: 0.5, stagger: 0.12, ease: "back.out(2.4)" }, 1.4)
          .from(q("[data-card]"), { opacity: 0, y: 34, scale: 0.95, filter: "blur(10px)", stagger: 0.16, duration: 1 }, 1.5)
          .from(q("[data-bar]"), { scaleY: 0, transformOrigin: "50% 100%", stagger: 0.035, duration: 0.7, ease: "back.out(1.6)" }, 1.9);

        // compliance figure counts up
        const figure = q("[data-rate]")[0];
        if (figure) {
          const n = { v: 0 };
          figure.textContent = "0%";
          tl.to(n, { v: 92, duration: 1.6, ease: "power2.out", onUpdate: () => void (figure.textContent = `${Math.round(n.v)}%`) }, 1.8);
        }

        // scroll: cards float at different depths (the photo stays put: moving it inside its mask
        // would re-rasterise the whole masked layer every frame)
        const st = { trigger: root.current, start: "top top", end: "bottom top", scrub: 0.6 };
        q("[data-depth]").forEach((el) => {
          gsap.to(el, { y: -Number((el as HTMLElement).dataset.depth), ease: "none", scrollTrigger: st });
        });
        gsap.to(q("[data-copy]"), { y: -50, ease: "none", scrollTrigger: st });
      });
      return () => mm.revert();
    },
    { scope: root },
  );

  return (
    <section
      ref={root}
      id="home"
      className="relative isolate overflow-hidden lg:min-h-[var(--hero-h)]"
      style={{ "--hero-w": "min(64vw, calc((100svh - 150px) * 1.219), 1180px)", "--hero-h": "calc(var(--hero-w) / 1.219)" } as CSSProperties}
    >
      {/* ---------------- photo + live cards (desktop) */}
      <div
        className="absolute top-0 right-0 hidden w-[var(--hero-w)] [container-type:inline-size] lg:block"
        style={{ aspectRatio: "896 / 735" }}
      >
        {/* the photo melts into the page on the left and bottom (a mask, so it matches either theme) */}
        <div
          data-photo-inner
          className="absolute inset-0 overflow-hidden [mask-composite:intersect] [mask-image:linear-gradient(90deg,transparent_0%,rgb(0_0_0/0.45)_12%,black_30%),linear-gradient(0deg,transparent_0%,black_15%)] [-webkit-mask-composite:source-in]"
        >
          <Image
            data-photo-img
            src="/images/hero-photo.webp"
            alt={t("Haul truck carrying coal in an open-cast mine at sunrise")}
            fill
            priority
            loading="eager"
            sizes="64vw"
            className="object-cover"
          />
          <div className="absolute inset-0 bg-black/0 transition-colors dark:bg-black/35" />
          <div className="absolute inset-0 hidden dark:block">
            <Backdrop kind="rays" origin="top-left" intensity={0.5} glow={false} className="mix-blend-screen" />
          </div>
          <Backdrop kind="dust" intensity={0.55} glow={false} />
        </div>

        {/* connector lines and nodes (comp geometry, 896 × 735 space) */}
        <svg viewBox="0 0 896 735" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
          {["M280 386 H224 V508", "M528 383 H730", "M782 216 H828 V383 H730", "M730 383 V592"].map((d) => (
            <path key={d} data-draw d={d} fill="none" stroke="white" strokeOpacity="0.75" strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        <Node x={25} y={58.5} />
        <Node x={81.5} y={52.1} />

        {/* AI insights */}
        <div data-depth="70" className="absolute will-change-transform" style={{ left: "54.5%", top: "26.6%", width: "32.9%", height: "21.3%" }}>
          <div data-card className="glass-solid group flex h-full items-stretch justify-between gap-[2cqw] rounded-[2.4cqw] p-[2.4cqw] shadow-[0_2.5cqw_5cqw_-2cqw_rgb(40_25_15/0.45)] transition-transform duration-500 hover:-translate-y-[0.5cqw]">
            <div className="flex min-w-0 flex-col justify-between">
              <p className="text-[1.25cqw] font-semibold tracking-[0.28em] text-muted uppercase">{t("AI Insights")}</p>
              <p className="text-[1.6cqw] leading-snug font-medium text-ink">{t("Potential safety risk detected in Zone B.")}</p>
              <Link href="/login" aria-label={t("Open AI insights")} className="grid h-[4.2cqw] w-[4.2cqw] place-items-center rounded-full bg-copper-600 text-white transition group-hover:rotate-45 group-hover:bg-copper-500">
                <ArrowUpRight className="h-[2cqw] w-[2cqw]" />
              </Link>
            </div>
            <div className="relative aspect-[11/10] h-full shrink-0 overflow-hidden rounded-[1.3cqw]">
              <Image
                src="/images/hero-photo.webp"
                alt=""
                fill
                sizes="30vw"
                className="scale-[4.2] object-cover transition duration-700 group-hover:scale-[4.6]"
                style={{ transformOrigin: "94.5% 69%" }}
              />
            </div>
          </div>
        </div>

        {/* compliance rate */}
        <div data-depth="40" className="absolute will-change-transform" style={{ left: "31.2%", top: "40.4%", width: "27.8%", height: "22.2%" }}>
          <div data-card className="glass-solid flex h-full flex-col rounded-[2.4cqw] p-[2.4cqw] shadow-[0_2.5cqw_5cqw_-2cqw_rgb(40_25_15/0.45)] transition-transform duration-500 hover:-translate-y-[0.5cqw]">
            <p className="text-[1.55cqw] text-steel-600">{t("Compliance Rate")}</p>
            <div className="mt-[0.6cqw] flex items-center gap-[1.2cqw]">
              <span data-rate className="font-display text-[3.2cqw] leading-none font-bold text-ink">92%</span>
              <span className="rounded-full bg-ok-soft px-[0.9cqw] py-[0.3cqw] text-[1.15cqw] font-semibold text-ok">↑ 6%</span>
            </div>
            <div className="mt-auto flex h-[7cqw] items-end gap-[0.8cqw]">
              {BARS.map((h, i) => (
                <span
                  key={i}
                  data-bar
                  className="flex-1 rounded-t-[0.3cqw] bg-gradient-to-t from-copper-500/80 to-copper-300/70"
                  style={{ height: `${h}%`, opacity: 0.35 + (i / BARS.length) * 0.65 }}
                />
              ))}
            </div>
          </div>
        </div>

        {/* inspection summary */}
        <div data-depth="20" className="absolute will-change-transform" style={{ left: "20%", top: "69%", width: "21.6%", height: "13.4%" }}>
          <div data-card className="glass-solid group flex h-full flex-col justify-between rounded-[2.2cqw] px-[2cqw] py-[1.6cqw] shadow-[0_2.5cqw_5cqw_-2cqw_rgb(40_25_15/0.45)] transition-transform duration-500 hover:-translate-y-[0.5cqw]">
            <p className="text-[1.45cqw] text-steel-600">{t("Inspection Summary")}</p>
            <div className="flex items-center gap-[1.4cqw]">
              <FileText className="h-[3cqw] w-[3cqw] shrink-0 text-ink" strokeWidth={1.4} />
              <div className="min-w-0 flex-1 leading-tight whitespace-nowrap">
                <p className="text-[1.6cqw] font-semibold text-ink">{t("24 reports")}</p>
                <p className="text-[1.1cqw] text-muted">{t("This month")}</p>
              </div>
              <Link href="/login" aria-label={t("Open inspections")} className="grid h-[3.4cqw] w-[3.4cqw] place-items-center rounded-full bg-copper-600 text-white transition group-hover:translate-x-[0.4cqw]">
                <ArrowRight className="h-[1.7cqw] w-[1.7cqw]" />
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* ---------------- copy */}
      <div data-copy className="relative z-10 mx-auto max-w-[1500px] px-5 pt-28 pb-8 sm:px-8 lg:px-14 lg:pt-[clamp(104px,13svh,150px)] lg:pb-[clamp(1.5rem,5svh,3.5rem)]">
        <div className="max-w-[640px]">
          <p data-eyebrow className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-semibold tracking-[0.32em] text-muted uppercase sm:text-xs">
            <span>{t("Smart Governance")}</span>
            <span className="text-copper-500">•</span>
            <span>{t("Safer Mines")}</span>
            <span className="text-copper-500">•</span>
            <span>{t("Sustainable Tomorrow")}</span>
          </p>

          <h1 className="mt-5">
            <span className="sr-only">{`LUMEN — ${t("For a cleaner,")} ${t("safer India")}`}</span>
            <span aria-hidden className="-mb-[0.06em] block overflow-hidden pb-[0.06em]">
              <span className="block font-display text-[clamp(4.2rem,min(10.4vw,16.5svh),10.2rem)] leading-[0.84] font-black tracking-[-0.055em]">
                {"LUMEN".split("").map((c, i) => (
                  <span
                    key={i}
                    data-char
                    className="brand-fill inline-block"
                    // one gradient across the word, sliced per letter so each can move on its own
                    style={{ backgroundSize: "500% 100%", backgroundPosition: `${i * 25}% 0` }}
                  >
                    {c}
                  </span>
                ))}
              </span>
            </span>
            <span aria-hidden className="relative mt-3 block font-display text-[clamp(2.2rem,min(4.8vw,7.6svh),4.7rem)] leading-[1] font-light tracking-[-0.035em] text-ink uppercase">
              <span className="block overflow-hidden pb-[0.08em]">
                <span data-tag className="block">{t("For a cleaner,")}</span>
              </span>
              <span className="relative inline-block overflow-hidden pb-[0.08em]">
                <span data-tag className="block">{t("safer India")}</span>
              </span>
              <svg viewBox="0 0 320 24" className="absolute -bottom-3 left-0 h-[0.32em] w-[4.2em] overflow-visible text-copper-500" aria-hidden>
                <path data-swoosh d="M3 16 C 70 4, 160 2, 316 12" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
              </svg>
            </span>
          </h1>

          <p data-fade className="mt-[clamp(1.25rem,3.4svh,2rem)] max-w-[560px] text-[16px] leading-relaxed text-muted sm:text-[clamp(16px,2.1svh,19px)]">
            {t("An AI-based governance and compliance monitoring platform for coal mines under the Ministry of Coal.")}
          </p>

          <div data-fade className="mt-[clamp(1.25rem,3.6svh,2.25rem)] flex flex-wrap items-center gap-4">
            <Magnetic strength={5}>
              <Spark>
                <Link
                  href="/login"
                  className="group relative inline-flex h-14 items-center gap-2.5 overflow-hidden rounded-xl bg-gradient-to-b from-copper-500 to-copper-700 px-10 text-[16px] font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_16px_36px_-14px_rgb(176_100_47/0.95)] transition hover:brightness-110"
                >
                  <span aria-hidden className="absolute inset-y-0 -left-1/2 w-1/3 -skew-x-12 bg-white/25 blur-md transition-all duration-700 group-hover:left-[120%]" />
                  {t("Get Started")}
                  <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
                </Link>
              </Spark>
            </Magnetic>
            <button
              type="button"
              onClick={onTour}
              className="group inline-flex h-14 items-center gap-3 rounded-xl border border-line-strong bg-surface/60 px-7 text-[16px] font-semibold text-ink backdrop-blur transition hover:border-copper-500/50 hover:bg-surface"
            >
              <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-ink transition group-hover:scale-110 group-hover:border-copper-500 group-hover:bg-copper-500 group-hover:text-white">
                <Play className="ml-0.5 h-3 w-3 fill-current" />
              </span>
              {t("Watch Video")}
            </button>
          </div>

          <ul className="mt-[clamp(1.75rem,5svh,3rem)] grid grid-cols-2 gap-x-6 gap-y-5 sm:flex sm:flex-nowrap sm:gap-x-6 lg:w-[max-content]">
            {FEATURES.map(({ icon: Icon, a, b }) => (
              <li key={a} data-feature className="group flex items-center gap-3">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl border border-copper-500/15 bg-copper-50 text-copper-500 transition duration-300 group-hover:-translate-y-0.5 group-hover:rotate-[-6deg] group-hover:bg-copper-500 group-hover:text-white">
                  <Icon className="h-[22px] w-[22px]" strokeWidth={1.6} />
                </span>
                <span className="text-[13.5px] leading-tight whitespace-nowrap text-ink">
                  {t(a)}
                  <br />
                  {t(b)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ---------------- photo (phones / tablets) */}
      <div className="relative mx-3 mb-4 overflow-hidden rounded-3xl lg:hidden" style={{ aspectRatio: "1090 / 620" }}>
        <Image src="/images/hero-photo-mobile.webp" alt="" fill sizes="(min-width: 1024px) 1px, 100vw" className="object-cover object-bottom" />
        <div className="absolute inset-0 dark:bg-black/30" />
        <div className="glass absolute bottom-4 left-4 rounded-2xl px-4 py-3">
          <p className="text-xs text-steel-600">{t("Compliance Rate")}</p>
          <p className="font-display text-2xl font-bold text-ink">92%</p>
        </div>
      </div>
    </section>
  );
}

function Node({ x, y }: { x: number; y: number }) {
  return (
    <span data-dot className="absolute grid h-[3cqw] w-[3cqw] -translate-x-1/2 -translate-y-1/2 place-items-center" style={{ left: `${x}%`, top: `${y}%` }}>
      <span className="absolute inset-0 rounded-full bg-white/40 motion-safe:animate-ping [animation-duration:2.6s]" />
      <span className="relative h-[1.9cqw] w-[1.9cqw] rounded-full bg-white shadow-[0_0_0_0.9cqw_rgb(255_255_255/0.25),0_0_2cqw_rgb(255_255_255/0.6)]" />
    </span>
  );
}

// -------------------------------------------------------------- impact band
const IMPACT: { icon: LucideIcon; value: number; suffix: string; a: string; b: string }[] = [
  { icon: Mountain, value: 450, suffix: "+", a: "Coal Mines", b: "Monitored" },
  { icon: ClipboardCheck, value: 10000, suffix: "+", a: "Inspections", b: "Digitized" },
  { icon: Sprout, value: 40, suffix: "%", a: "Faster", b: "Compliance" },
];

export function ImpactBand({ onTour }: { onTour: () => void }) {
  const { t } = useI18n();
  const root = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const q = gsap.utils.selector(root);
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const tl = gsap.timeline({ scrollTrigger: { trigger: root.current, start: "top 85%", once: true } });
        tl.from(q("[data-band]"), { y: 60, opacity: 0, stagger: 0.14, duration: 1, ease: "power3.out" })
          .from(q("[data-stat]"), { y: 20, opacity: 0, stagger: 0.1, duration: 0.7, ease: "power3.out" }, 0.3);
        q("[data-count]").forEach((el) => {
          const target = Number((el as HTMLElement).dataset.count);
          const suffix = (el as HTMLElement).dataset.suffix ?? "";
          const n = { v: 0 };
          el.textContent = `0${suffix}`;
          tl.to(n, { v: target, duration: 1.8, ease: "power2.out", onUpdate: () => void (el.textContent = `${Math.round(n.v).toLocaleString("en-IN")}${suffix}`) }, 0.4);
        });
      });
      return () => mm.revert();
    },
    { scope: root },
  );

  return (
    <section ref={root} aria-label={t("Impact")} className="relative z-10 mx-auto max-w-[1500px] px-3 pb-12 sm:px-6 lg:-mt-10 lg:px-10 lg:pb-16">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,47fr)_minmax(0,53fr)]">
        {/* story */}
        <div data-band className="group relative isolate min-h-[270px] overflow-hidden rounded-[22px] bg-coal-900 text-white">
          <Image src="/images/coal-texture.jpg" alt="" fill sizes="50vw" className="-z-10 object-cover opacity-70 transition duration-[1.6s] group-hover:scale-105" />
          <div className="absolute inset-0 -z-10 bg-[linear-gradient(90deg,rgb(16_12_10/0.92)_0%,rgb(16_12_10/0.6)_55%,rgb(16_12_10/0.25)_100%)]" />
          <span aria-hidden className="absolute top-0 bottom-0 left-[66%] hidden w-px bg-white/10 sm:block" />
          <div className="relative flex h-full flex-col justify-center p-8 max-sm:pb-6 sm:p-10">
            <h2 className="font-display leading-[1.12]">
              <span className="block text-[30px] font-light text-white/85 sm:text-[34px]">{t("From")}</span>
              <span className="block text-[30px] font-bold sm:text-[34px]">{t("Regulation")}</span>
              <span className="block text-[30px] font-bold sm:text-[34px]">{t("to Real Impact")}</span>
            </h2>
            <span className="mt-5 block h-px w-8 bg-white/60" />
            <p className="mt-5 max-w-[330px] text-[15px] leading-relaxed text-white/75">
              {t("Leveraging AI and digital tools to ensure compliance, improve safety, and build a sustainable coal sector.")}
            </p>
          </div>
          <button
            type="button"
            onClick={onTour}
            className="relative mx-8 mb-8 flex items-center gap-3 text-sm font-semibold sm:absolute sm:top-1/2 sm:left-[66%] sm:m-0 sm:-translate-x-7 sm:-translate-y-1/2"
          >
            <span className="relative grid h-14 w-14 place-items-center rounded-full bg-white text-coal-900 shadow-[0_0_0_10px_rgb(255_255_255/0.12)] transition duration-300 group-hover:scale-110">
              <span className="absolute inset-0 rounded-full border border-white/60 motion-safe:animate-ping [animation-duration:2.4s]" />
              <Play className="ml-0.5 h-5 w-5 fill-current" />
            </span>
            {t("Watch Our Story")}
          </button>
        </div>

        {/* stats + call to action */}
        <div data-band className="flex flex-col gap-4 rounded-[22px] bg-canvas p-4 sm:p-6 lg:rounded-tl-[72px] lg:pl-10">
          <div className="grid grid-cols-1 gap-5 py-2 sm:grid-cols-3 sm:gap-0 sm:divide-x sm:divide-line-strong">
            {IMPACT.map(({ icon: Icon, value, suffix, a, b }) => (
              <div key={a} data-stat className="group flex items-center gap-4 sm:justify-center sm:px-4">
                <span className="grid h-14 w-14 shrink-0 place-items-center rounded-xl bg-copper-50 text-copper-500 transition duration-300 group-hover:scale-105 group-hover:bg-copper-500 group-hover:text-white">
                  <Icon className="h-7 w-7" strokeWidth={1.5} />
                </span>
                <div>
                  <p data-count={value} data-suffix={suffix} className="font-display text-[30px] leading-none font-bold tracking-[-0.03em] text-ink tabular-nums">
                    {value.toLocaleString("en-IN")}
                    {suffix}
                  </p>
                  <p className="mt-1.5 text-sm leading-tight text-steel-600">
                    {t(a)}
                    <br />
                    {t(b)}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <Link
            href="/login"
            className="group relative isolate flex flex-col gap-5 overflow-hidden rounded-[22px] bg-[linear-gradient(110deg,#3b2a1f_0%,#2c1f16_55%,#231811_100%)] p-6 text-white sm:flex-row sm:items-center sm:gap-8 sm:px-9 sm:py-7"
          >
            <span aria-hidden className="absolute -top-20 -right-16 -z-10 h-56 w-56 rounded-full bg-copper-500/25 blur-3xl transition duration-700 group-hover:bg-copper-500/40" />
            <Image src="/images/team.png" alt={t("Mine worker, officer and engineer")} width={158} height={68} className="h-16 w-auto shrink-0 transition duration-500 group-hover:-translate-y-0.5" />
            <div className="min-w-0 flex-1">
              <p className="font-display text-[24px] leading-tight font-medium sm:text-[26px]">
                {t("A Safer, Cleaner")}
                <br />
                {t("and Stronger Coal Sector")}
              </p>
              <p className="mt-2 text-sm text-white/70">{t("Through technology, transparency and collaboration.")}</p>
            </div>
            <span className="hidden h-14 w-px bg-white/15 sm:block" />
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full border border-white/50 transition duration-300 group-hover:border-copper-400 group-hover:bg-copper-500">
              <ArrowRight className="h-5 w-5 transition group-hover:translate-x-0.5" />
            </span>
          </Link>
        </div>
      </div>
    </section>
  );
}

// -------------------------------------------------------------------- tour
const TOUR_MS = 5200;

/** "Watch" opens a short, self-playing walkthrough of how Lumen works. */
export function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const [cycle, setCycle] = useState(0);
  const go = (d: number) => {
    setStep((s) => (s + d + STEPS.length) % STEPS.length);
    setCycle((c) => c + 1);
  };

  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(() => setStep((s) => (s + 1) % STEPS.length), TOUR_MS);
    return () => window.clearTimeout(id);
  }, [open, step, cycle]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  });

  const s = STEPS[step];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[70] grid place-items-center bg-black/65 p-3 backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t("How Lumen works")}
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.97 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="relative grid grid-cols-1 w-full max-w-5xl overflow-hidden rounded-[28px] border border-fg/10 bg-raised shadow-[0_40px_120px_-20px_rgb(0_0_0/0.8)] md:grid-cols-[1.1fr_1fr]"
          >
            <div className="relative isolate aspect-[4/3] overflow-hidden bg-coal-900 md:aspect-auto md:min-h-[440px]">
              <AnimatePresence mode="wait">
                <motion.div
                  key={step}
                  initial={{ opacity: 0, scale: 1.08 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.8 }}
                  className="absolute inset-0 -z-10"
                >
                  <Image
                    src={["/images/login/slide-4.webp", "/images/hero-photo.webp", "/images/login/slide-2.webp", "/images/login/slide-1.webp"][step]}
                    alt=""
                    fill
                    sizes="50vw"
                    className="object-cover object-right"
                  />
                </motion.div>
              </AnimatePresence>
              <div className="absolute inset-0 -z-10 bg-gradient-to-t from-black/70 via-black/20 to-black/10" />
              <Backdrop kind="dust" intensity={0.7} glow={false} />
              <div className="absolute bottom-6 left-6 flex items-center gap-3 text-white">
                <span className="grid h-14 w-14 place-items-center rounded-2xl bg-copper-500 shadow-[0_12px_30px_-10px_rgb(212_136_78/0.9)]">
                  <s.icon className="h-6 w-6" />
                </span>
                <span className="font-display text-6xl leading-none font-black text-white/90">{s.code}</span>
              </div>
            </div>

            <div className="flex flex-col p-7 sm:p-9">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold tracking-[0.24em] text-copper-500 uppercase">{t("How Lumen works")}</p>
                <button onClick={onClose} className="grid h-10 w-10 place-items-center rounded-full text-muted transition hover:bg-fg/5 hover:text-ink" aria-label={t("Close")}>
                  <X className="h-5 w-5" />
                </button>
              </div>
              <AnimatePresence mode="wait">
                <motion.div
                  key={step}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.35 }}
                  className="mt-8 flex-1"
                >
                  <h3 className="font-display text-4xl font-bold tracking-tight text-ink">
                    <Split text={t(s.title)} by="chars" delay={30} />
                  </h3>
                  <p className="mt-4 text-[17px] leading-relaxed text-muted">{t(s.body)}</p>
                </motion.div>
              </AnimatePresence>

              <div className="mt-8 flex gap-2" role="tablist" aria-label={t("Steps")}>
                {STEPS.map((x, i) => (
                  <button
                    key={x.code}
                    role="tab"
                    aria-selected={i === step}
                    aria-label={t(x.title)}
                    onClick={() => {
                      setStep(i);
                      setCycle((c) => c + 1);
                    }}
                    className="h-6 flex-1 py-2.5"
                  >
                    <span className="block h-1 overflow-hidden rounded-full bg-fg/10">
                      {i < step && <span className="block h-full w-full bg-copper-500/60" />}
                      {i === step && (
                        <motion.span
                          key={`${step}-${cycle}`}
                          className="block h-full origin-left bg-copper-500"
                          initial={{ scaleX: 0 }}
                          animate={{ scaleX: 1 }}
                          transition={{ duration: TOUR_MS / 1000, ease: "linear" }}
                        />
                      )}
                    </span>
                  </button>
                ))}
              </div>
              <div className="mt-5 flex items-center gap-2">
                <button onClick={() => go(-1)} className="grid h-11 w-11 place-items-center rounded-full border border-line-strong text-ink transition hover:bg-fg/5" aria-label={t("Previous")}>
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button onClick={() => go(1)} className="grid h-11 w-11 place-items-center rounded-full border border-line-strong text-ink transition hover:bg-fg/5" aria-label={t("Next")}>
                  <ChevronRight className="h-5 w-5" />
                </button>
                <Link href="/login" className={cn("ml-auto inline-flex h-11 items-center gap-2 rounded-full bg-copper-600 px-5 text-sm font-semibold text-white transition hover:brightness-110")}>
                  {t("Get Started")} <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
