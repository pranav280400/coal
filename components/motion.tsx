"use client";

/**
 * Lumen motion kit — small, calm animations adapted from React Bits (reactbits.dev):
 * CountUp, FadeContent, AnimatedList, BlurText and SpotlightCard.
 *
 * Rules for a government platform: every effect runs once, lasts well under a second,
 * moves at most a few pixels, never loops, and is switched off entirely when the user
 * asks their system to reduce motion.
 */

import { motion, useInView, useMotionValue, useReducedMotion, useSpring } from "motion/react";
import {
  Children,
  isValidElement,
  useEffect,
  useRef,
  type CSSProperties,
  type MouseEvent,
  type ReactNode,
} from "react";
import { cn } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

const EASE = [0.22, 1, 0.36, 1] as const; // ease-out-quint: quick start, soft landing

// ------------------------------------------------------------------ CountUp
/** Counts from `from` to `value` once, when the number scrolls into view (React Bits CountUp). */
export function CountUp({
  value,
  from = 0,
  duration = 1.1,
  decimals,
  prefix = "",
  suffix = "",
  className,
}: {
  value: number;
  from?: number;
  duration?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduce = useReducedMotion();
  const places = decimals ?? (Number.isInteger(value) ? 0 : Math.min(2, String(value).split(".")[1]?.length ?? 0));
  const fmt = (n: number) =>
    prefix + new Intl.NumberFormat("en-IN", { minimumFractionDigits: places, maximumFractionDigits: places }).format(n) + suffix;
  const mv = useMotionValue(reduce ? value : from);
  const spring = useSpring(mv, { damping: 20 + 40 / duration, stiffness: 100 / duration });
  const inView = useInView(ref, { once: true, margin: "0px 0px -40px 0px" });

  useEffect(() => {
    if (reduce) {
      if (ref.current) ref.current.textContent = fmt(value);
      return;
    }
    if (inView) mv.set(value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, value, reduce]);

  useEffect(
    () =>
      spring.on("change", (v) => {
        if (ref.current) ref.current.textContent = fmt(v);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [spring, places, prefix, suffix],
  );

  return (
    <span ref={ref} className={cn("tabular-nums", className)}>
      {fmt(reduce ? value : from)}
    </span>
  );
}

/**
 * Animates the leading number of a display string ("93%", "8.04 Mt", "1,234") and keeps the rest.
 * Non-numeric values ("—") are shown as they are.
 */
export function CountUpText({ text, className }: { text: string; className?: string }) {
  const m = /^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/.exec(text);
  if (!m) return <span className={className}>{text}</span>;
  const raw = m[2].replace(/,/g, "");
  const value = Number(raw);
  if (!Number.isFinite(value)) return <span className={className}>{text}</span>;
  const decimals = raw.includes(".") ? raw.split(".")[1].length : 0;
  return <CountUp value={value} decimals={decimals} prefix={m[1]} suffix={m[3]} className={className} />;
}

/** Counts up a stat that may arrive as a number, a display string ("93%") or a placeholder ("—"). */
export function CountUpValue({ value }: { value: ReactNode }) {
  if (typeof value === "number") return <CountUp value={value} />;
  if (typeof value === "string") return <CountUpText text={value} />;
  return <>{value}</>;
}

// -------------------------------------------------------------- FadeContent
/** Fades content in and lifts it a few pixels the first time it scrolls into view (React Bits FadeContent). */
export function FadeContent({
  children,
  delay = 0,
  y = 8,
  duration = 0.45,
  className,
  as = "div",
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  duration?: number;
  className?: string;
  as?: "div" | "section" | "li";
}) {
  const reduce = useReducedMotion();
  const Tag = motion[as];
  if (reduce) {
    const Plain = as;
    return <Plain className={className}>{children}</Plain>;
  }
  return (
    <Tag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -40px 0px" }}
      transition={{ duration, delay, ease: EASE }}
    >
      {children}
    </Tag>
  );
}

// ------------------------------------------------------------- AnimatedList
/**
 * Reveals direct children one after another (React Bits AnimatedList, toned down:
 * a short fade and 6px rise instead of a scale-up, 45 ms apart, once).
 */
export function AnimatedList({
  children,
  className,
  step = 0.045,
  as = "ul",
}: {
  children: ReactNode;
  className?: string;
  step?: number;
  as?: "ul" | "div" | "ol";
}) {
  const reduce = useReducedMotion();
  const Tag = motion[as];
  if (reduce) {
    const Plain = as;
    return (
      <Plain className={className}>
        {as === "div" ? children : Children.map(children, (c) => (isValidElement(c) ? <li>{c}</li> : c))}
      </Plain>
    );
  }
  return (
    <Tag
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "0px 0px -30px 0px" }}
      variants={{ show: { transition: { staggerChildren: step } } }}
    >
      {Children.map(children, (child) => {
        if (!isValidElement(child)) return child;
        // Lists get <li> wrappers (callers pass the item's content, not an <li>).
        const Item = as === "div" ? motion.div : motion.li;
        return (
          <Item variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE } } }}>
            {child}
          </Item>
        );
      })}
    </Tag>
  );
}

/** Wraps one grid/list item so it takes part in a parent `Stagger`. */
export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      className={className}
      variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE } } }}
    >
      {children}
    </motion.div>
  );
}

/** Container that reveals its `StaggerItem`s in sequence the first time it enters the viewport. */
export function Stagger({ children, className, step = 0.06 }: { children: ReactNode; className?: string; step?: number }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "0px 0px -40px 0px" }}
      variants={{ show: { transition: { staggerChildren: step } } }}
    >
      {children}
    </motion.div>
  );
}

// ----------------------------------------------------------------- BlurText
/** Words sharpen into place one after another, once (React Bits BlurText, short and subtle). */
export function BlurText({ text, className, delay = 0.06, as = "span" }: { text: string; className?: string; delay?: number; as?: "span" | "h1" | "p" }) {
  const reduce = useReducedMotion();
  const Tag = as;
  if (reduce) return <Tag className={className}>{text}</Tag>;
  const words = text.split(" ");
  return (
    <Tag className={className} aria-label={text}>
      {words.map((w, i) => (
        <motion.span
          key={`${w}-${i}`}
          aria-hidden
          className="inline-block will-change-[filter,opacity]"
          initial={{ filter: "blur(8px)", opacity: 0, y: 6 }}
          animate={{ filter: "blur(0px)", opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: i * delay, ease: EASE }}
        >
          {w}
          {i < words.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </Tag>
  );
}

// ------------------------------------------------------------ SpotlightCard
/** A faint copper glow follows the pointer — a hover cue for clickable cards (React Bits SpotlightCard). */
export function useSpotlight(color = "rgba(184, 107, 53, 0.10)") {
  // Position goes into CSS variables on the card itself: no React re-render per mouse move.
  const handlers = {
    onMouseMove: (e: MouseEvent<HTMLElement>) => {
      const el = e.currentTarget;
      const r = el.getBoundingClientRect();
      el.style.setProperty("--sx", `${e.clientX - r.left}px`);
      el.style.setProperty("--sy", `${e.clientY - r.top}px`);
      el.style.setProperty("--so", "1");
    },
    onMouseLeave: (e: MouseEvent<HTMLElement>) => e.currentTarget.style.setProperty("--so", "0"),
  };
  const glow: CSSProperties = {
    opacity: "var(--so, 0)",
    background: `radial-gradient(260px circle at var(--sx, 50%) var(--sy, 50%), ${color}, transparent 70%)`,
  };
  const layer = <span aria-hidden className="pointer-events-none absolute inset-0 rounded-[inherit] transition-opacity duration-300" style={glow} />;
  return { handlers, layer };
}

export function SpotlightCard({ children, className, color }: { children: ReactNode; className?: string; color?: string }) {
  const { handlers, layer } = useSpotlight(color);
  return (
    <div className={cn("relative overflow-hidden", className)} {...handlers}>
      {layer}
      <div className="relative">{children}</div>
    </div>
  );
}

// ------------------------------------------------------------------ GrowBar
/** A progress bar that grows to its value once it is visible, so the eye reads it as a quantity. */
export function GrowBar({ pct, className, barClassName }: { pct: number; className?: string; barClassName?: string }) {
  const reduce = useReducedMotion();
  const width = `${Math.max(0, Math.min(100, pct))}%`;
  return (
    <div className={cn("overflow-hidden rounded-full bg-fg/[0.06]", className)}>
      {reduce ? (
        <div className={cn("h-full rounded-full", barClassName)} style={{ width }} />
      ) : (
        <motion.div
          className={cn("h-full rounded-full", barClassName)}
          initial={{ width: 0 }}
          whileInView={{ width }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, ease: EASE }}
        />
      )}
    </div>
  );
}

/** BlurText for server-rendered pages: translates the text first (EN / हि). */
export function BlurT({ text, className }: { text: string; className?: string }) {
  const { t } = useI18n();
  return <BlurText text={t(text)} className={className} />;
}
