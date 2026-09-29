"use client";

import { ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Logo } from "@/components/brand";
import { Backdrop } from "@/components/fx";
import { LangToggle } from "@/components/lang-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

/**
 * Sign-in layout: an aurora-lit form column (left) and the mine photo slideshow in an
 * inset rounded frame (right), with story-style progress bars that fill as each slide plays.
 * Slides are the photo panels of public/images/l1–l4, cropped to public/images/login/slide-N.webp.
 */

const SLIDES = [
  { src: "/images/login/slide-1.webp", alt: "Wheel loader working on a coal stockpile" },
  { src: "/images/login/slide-2.webp", alt: "Open-cast coal mine at sunset" },
  { src: "/images/login/slide-3.webp", alt: "Dumpers on a haul road in an open-cast mine" },
  { src: "/images/login/slide-4.webp", alt: "Mine worker at the coal face" },
];
const INTERVAL_MS = 6000;

function Slideshow() {
  const { t } = useI18n();
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  // Bumped on every manual jump so the progress bar restarts from zero.
  const [cycle, setCycle] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const restart = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(() => setActive((i) => (i + 1) % SLIDES.length), INTERVAL_MS);
  }, []);

  useEffect(() => {
    if (paused) {
      if (timer.current) clearInterval(timer.current);
      return;
    }
    restart();
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [paused, restart]);

  // Don't advance while the tab is in the background.
  useEffect(() => {
    const onVis = () => setPaused(document.hidden);
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  return (
    <aside
      className="relative hidden p-3 lg:block"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-roledescription="carousel"
      aria-label={t("Coal mining operations")}
    >
      <div className="relative h-full overflow-hidden rounded-[28px] border border-fg/[0.08] bg-coal-900">
        {SLIDES.map((s, i) => (
          <div
            key={s.src}
            className={cn("absolute inset-0 transition-opacity duration-[1400ms] ease-in-out", i === active ? "z-10 opacity-100" : "z-0 opacity-0")}
            aria-hidden={i !== active}
          >
            <Image
              src={s.src}
              alt={s.alt}
              fill
              priority={i === 0}
              // Load every slide up front so the cross-fade never reveals an empty frame.
              loading="eager"
              // Already web-sized WebP: serve as-is so the first slide appears immediately.
              unoptimized
              sizes="60vw"
              // Anchored left so the headline printed on each photo is never cropped.
              className={cn("object-cover object-left", i === active && "animate-kenburns")}
            />
          </div>
        ))}
        <div className="pointer-events-none absolute inset-0 z-20 bg-[linear-gradient(to_top,rgb(10_11_12/0.75),transparent_35%),linear-gradient(to_right,rgb(10_11_12/0.35),transparent_30%)]" />

        {/* top-right status chip */}
        <div className="glass absolute top-5 right-5 z-30 flex items-center gap-2 rounded-full px-3.5 py-2 text-xs font-medium text-ink">
          <span className="h-1.5 w-1.5 rounded-full bg-ok shadow-[0_0_10px_#34c77b] motion-safe:animate-pulse" />
          {t("Secure government system")}
        </div>

        {/* story-style progress: the active bar fills over the slide's duration */}
        <div className="absolute inset-x-8 bottom-8 z-30 flex gap-2" role="tablist" aria-label={t("Slides")}>
          {SLIDES.map((s, i) => (
            <button
              key={s.src}
              type="button"
              role="tab"
              aria-selected={i === active}
              aria-label={`${t("Slide")} ${i + 1}`}
              onClick={() => {
                setActive(i);
                setCycle((c) => c + 1);
                restart();
              }}
              className="group h-5 flex-1 py-2"
            >
              <span className="block h-1 overflow-hidden rounded-full bg-white/20 transition group-hover:bg-white/35">
                {i < active && <span className="block h-full w-full bg-white/70" />}
                {i === active && !paused && (
                  <motion.span
                    key={`${active}-${cycle}`}
                    className="block h-full origin-left bg-copper-400 shadow-[0_0_10px_#e3a473]"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: INTERVAL_MS / 1000, ease: "linear" }}
                  />
                )}
                {i === active && paused && <span className="block h-full w-full bg-copper-400/80" />}
              </span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

function MinistryHeader() {
  return (
    <div className="flex items-center gap-4">
      <Image src="/images/emblem.png" alt="State Emblem of India" width={52} height={80} className="h-[64px] w-auto dark:invert" priority />
      <div className="border-l border-fg/10 pl-4 leading-tight">
        <p className="text-[17px] font-bold text-ink" lang="hi">कोयला मंत्रालय</p>
        <p className="font-display text-[19px] font-bold tracking-tight text-ink">Ministry of Coal</p>
        <p className="text-[13px] text-muted">Government of India</p>
      </div>
    </div>
  );
}

export function AuthFrame({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="min-h-dvh bg-canvas lg:grid lg:h-dvh lg:grid-cols-[minmax(480px,44%)_1fr]">
      <div className="grain relative isolate flex min-h-dvh flex-col overflow-hidden px-6 py-6 sm:px-12 lg:min-h-0 lg:overflow-y-auto">
        <Backdrop kind="aurora" intensity={0.55} className="-z-10 [mask-image:linear-gradient(to_bottom,black,transparent_70%)]" />

        <div className="flex items-center justify-between">
          <Link href="/" aria-label="Lumen home">
            <Logo size="sm" />
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <LangToggle size="sm" />
          </div>
        </div>

        <div className="mx-auto flex w-full max-w-[440px] flex-1 flex-col justify-center gap-10 py-10">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
            <MinistryHeader />
          </motion.div>
          <div>{children}</div>
        </div>

        <p className="flex items-center justify-center gap-2 text-center text-xs text-steel-500">
          <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-ok" />
          {t("Access is logged and monitored. Authorised users only.")}
        </p>
      </div>
      <Slideshow />
    </div>
  );
}
