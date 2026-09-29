"use client";

/**
 * Lumen FX — the React Bits components (components/reactbits) with Lumen's defaults:
 * copper-on-coal colours, calm speeds, and a static fallback whenever the user asks
 * their system to reduce motion. Pages import from here, never from reactbits directly.
 */

import { useReducedMotion } from "motion/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState, type ComponentProps, type ReactNode, type RefObject } from "react";
import ClickSpark from "@/components/reactbits/ClickSpark";
import DecryptedText from "@/components/reactbits/DecryptedText";
import Magnet from "@/components/reactbits/Magnet";
import RotatingText from "@/components/reactbits/RotatingText";
import ScrollReveal from "@/components/reactbits/ScrollReveal";
import ScrollVelocity from "@/components/reactbits/ScrollVelocity";
import ShinyText from "@/components/reactbits/ShinyText";
import SplitText from "@/components/reactbits/SplitText";
import StarBorder from "@/components/reactbits/StarBorder";
import TextType from "@/components/reactbits/TextType";
import { cn } from "@/components/ui";
import { useTheme } from "@/lib/theme";

// WebGL backgrounds load on the client only, after the page is interactive.
const LightRays = dynamic(() => import("@/components/reactbits/LightRays"), { ssr: false });
const Aurora = dynamic(() => import("@/components/reactbits/Aurora"), { ssr: false });
const Threads = dynamic(() => import("@/components/reactbits/Threads"), { ssr: false });
const Particles = dynamic(() => import("@/components/reactbits/Particles"), { ssr: false });

export const COPPER = { light: "#edc19b", base: "#d4884e", deep: "#c4733a", glow: "#e3a473" } as const;

// ------------------------------------------------------------ backgrounds
/**
 * True while the element is near the viewport and the tab is visible. Backgrounds mount
 * their WebGL canvas only then, so nothing renders off-screen or in a background tab.
 */
function useLive<T extends Element>(): [RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  const [shown, setShown] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { rootMargin: "200px 0px" });
    io.observe(el);
    const onVis = () => setShown(!document.hidden);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);
  return [ref, inView && shown];
}

/**
 * Animated background layer (React Bits LightRays / Aurora / Threads). Fills its
 * positioned parent; a static copper glow sits underneath so the section looks
 * finished before WebGL starts, and is all that shows with reduced motion.
 */
export function Backdrop({
  kind,
  className,
  intensity = 1,
  origin = "top-center",
  glow = true,
}: {
  kind: "rays" | "aurora" | "threads" | "dust";
  className?: string;
  intensity?: number;
  origin?: "top-center" | "top-left" | "top-right";
  glow?: boolean;
}) {
  const reduce = useReducedMotion();
  const light = useTheme() === "light";
  const [box, live] = useLive<HTMLDivElement>();
  const on = live && !reduce;
  return (
    <div ref={box} aria-hidden className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}>
      {glow && <div className="absolute inset-0 bg-[radial-gradient(900px_500px_at_50%_-10%,rgb(212_136_78/0.18),transparent_70%)]" />}
      {on && kind === "rays" && (
        <div className="absolute inset-0" style={{ opacity: 0.9 * intensity }}>
          <LightRays
            raysOrigin={origin}
            raysColor={light ? "#ffd9b0" : COPPER.glow}
            lightMode={light}
            raysSpeed={0.55}
            lightSpread={0.85}
            rayLength={1.6}
            fadeDistance={1.1}
            saturation={0.9}
            followMouse
            mouseInfluence={0.06}
            noiseAmount={0.06}
            distortion={0.03}
          />
        </div>
      )}
      {on && kind === "aurora" && (
        <div className="absolute inset-0" style={{ opacity: 0.75 * intensity }}>
          <Aurora
            colorStops={light ? ["#f3c9a1", "#e8a36d", "#f6e3cf"] : ["#7e4520", "#d4884e", "#2b3a4a"]}
            amplitude={0.9}
            blend={0.55}
            speed={0.5}
            lightMode={light}
          />
        </div>
      )}
      {on && kind === "threads" && (
        <div className="absolute inset-0" style={{ opacity: 0.55 * intensity }}>
          <Threads color={light ? [0.69, 0.39, 0.18] : [0.89, 0.64, 0.45]} amplitude={1.1} distance={0.2} enableMouseInteraction={false} />
        </div>
      )}
      {on && kind === "dust" && (
        <div className="absolute inset-0" style={{ opacity: intensity }}>
          <Particles
            particleCount={90}
            pixelRatio={1}
            particleSpread={12}
            speed={0.06}
            particleColors={light ? ["#ffffff", "#ffe2c2", "#e8a36d"] : ["#e3a473", "#edc19b", "#ffffff"]}
            particleBaseSize={70}
            sizeRandomness={1}
            alphaParticles
            disableRotation
            moveParticlesOnHover
            particleHoverFactor={0.4}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------- text effects
/** A light sweep across muted text (React Bits ShinyText) — for eyebrows and badges. */
export function Shiny({ text, className }: { text: string; className?: string }) {
  const reduce = useReducedMotion();
  const light = useTheme() === "light";
  return (
    <ShinyText
      text={text}
      disabled={!!reduce}
      speed={3.2}
      delay={1.2}
      color={light ? "#6a625b" : "#a3aab0"}
      shineColor={light ? "#c2773f" : "#ffffff"}
      spread={110}
      className={className}
    />
  );
}

/** Slowly drifting copper gradient fill for one or two emphasised words (React Bits GradientText, inline). */
export function CopperText({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block bg-[image:var(--copper-text)] bg-[length:300%_100%] bg-clip-text text-transparent motion-safe:animate-[copper-drift_9s_ease-in-out_infinite_alternate]",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Words cycling in place (React Bits RotatingText). */
export function Rotating({ texts, className, interval = 2800 }: { texts: string[]; className?: string; interval?: number }) {
  const reduce = useReducedMotion();
  if (reduce) return <span className={className}>{texts[0]}</span>;
  return (
    <RotatingText
      texts={texts}
      mainClassName={cn("inline-flex overflow-hidden", className)}
      splitLevelClassName="overflow-hidden pb-[0.1em]"
      staggerFrom="last"
      initial={{ y: "100%" }}
      animate={{ y: 0 }}
      exit={{ y: "-120%" }}
      staggerDuration={0.022}
      transition={{ type: "spring", damping: 30, stiffness: 380 }}
      rotationInterval={interval}
    />
  );
}

/** Characters resolve from scrambled glyphs when scrolled into view (React Bits DecryptedText). */
export function Decrypt({ text, className }: { text: string; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <span className={className}>{text}</span>;
  return (
    <DecryptedText
      text={text}
      animateOn="view"
      sequential
      revealDirection="start"
      speed={35}
      className={className}
      encryptedClassName="text-copper-500/70"
      characters="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&"
    />
  );
}

/** Letters or words rise into place once (React Bits SplitText). */
export function Split({
  text,
  className,
  tag = "span",
  by = "chars",
  delay = 22,
}: {
  text: string;
  className?: string;
  tag?: ComponentProps<typeof SplitText>["tag"];
  by?: "chars" | "words";
  delay?: number;
}) {
  const reduce = useReducedMotion();
  if (reduce) {
    const Tag = tag ?? "span";
    return <Tag className={className}>{text}</Tag>;
  }
  return (
    <SplitText
      text={text}
      tag={tag}
      splitType={by}
      delay={delay}
      duration={0.8}
      ease="power3.out"
      from={{ opacity: 0, y: 36 }}
      to={{ opacity: 1, y: 0 }}
      threshold={0.1}
      rootMargin="-40px"
      textAlign="inherit"
      // SplitText clips its box (overflow-hidden); pad it so descenders survive tight leading.
      className={cn("-mb-[0.14em] pb-[0.14em]", className)}
    />
  );
}

/** A statement whose words brighten as it scrolls through the viewport (React Bits ScrollReveal). */
export function Reveal({ children, className, textClassName }: { children: string; className?: string; textClassName?: string }) {
  const reduce = useReducedMotion();
  if (reduce) {
    return (
      <div className={className}>
        <p className={textClassName}>{children}</p>
      </div>
    );
  }
  return (
    <ScrollReveal baseOpacity={0.14} enableBlur={false} baseRotation={0} containerClassName={className} textClassName={textClassName}>
      {children}
    </ScrollReveal>
  );
}

/** Typewriter with a copper caret (React Bits TextType). */
export function Typing({ texts, className }: { texts: string[]; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <span className={className}>{texts[0]}</span>;
  return (
    <TextType
      text={texts}
      as="span"
      className={className}
      typingSpeed={38}
      deletingSpeed={22}
      pauseDuration={2200}
      cursorCharacter="▍"
      cursorClassName="text-copper-400"
      startOnVisible
    />
  );
}

/** Scroll-linked marquee (React Bits ScrollVelocity). */
export function Marquee({ items, className, velocity = 40 }: { items: ReactNode[]; className?: string; velocity?: number }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={cn("flex flex-wrap justify-center gap-x-10 gap-y-2", className)}>{items}</div>;
  return <ScrollVelocity texts={items} velocity={velocity} numCopies={4} className={className} />;
}

// ---------------------------------------------------- micro-interactions
/** Pulls its child gently toward the pointer (React Bits Magnet). */
export function Magnetic({ children, strength = 5, className }: { children: ReactNode; strength?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <Magnet padding={50} magnetStrength={strength} disabled={!!reduce} wrapperClassName={cn("inline-block", className)}>
      {children}
    </Magnet>
  );
}

/** A burst of copper sparks where the user clicks (React Bits ClickSpark). */
export function Spark({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <div className={className}>
      <ClickSpark sparkColor={COPPER.glow} sparkSize={9} sparkRadius={20} sparkCount={9} duration={450} extraScale={1}>
        {children}
      </ClickSpark>
    </div>
  );
}

/** Call-to-action link with a travelling star on its border (React Bits StarBorder). */
export function StarLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  const light = useTheme() === "light";
  return (
    <StarBorder
      as={Link}
      href={href}
      color={COPPER.glow}
      speed="5s"
      thickness={1}
      backgroundColor={light ? "#ffffff" : "#141619"}
      textColor={light ? "#1c1714" : "#f4f2ee"}
      borderColor={light ? "rgb(42 31 23 / 0.12)" : "rgb(255 255 255 / 0.1)"}
      className={cn("group [&>div:last-child]:!px-7 [&>div:last-child]:!py-[14px] [&>div:last-child]:!text-[15px] [&>div:last-child]:font-semibold", className)}
    >
      {children}
    </StarBorder>
  );
}

/**
 * Card whose border lights up copper around the pointer (React Bits BorderGlow / SpotlightCard,
 * rebuilt in CSS): the pointer position is written to CSS variables, so moving the mouse never
 * re-renders React, and the glow layers only exist while hovered. Styles: .glow-card in globals.css.
 */
export function GlowCard({ children, className, radius = 24 }: { children: ReactNode; className?: string; radius?: number }) {
  return (
    <div
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty("--gx", `${e.clientX - r.left}px`);
        e.currentTarget.style.setProperty("--gy", `${e.clientY - r.top}px`);
      }}
      className={cn("glow-card relative isolate border border-fg/[0.08] bg-surface shadow-card", className)}
      style={{ borderRadius: radius }}
    >
      <div className="relative z-[1] flex h-full flex-col">{children}</div>
    </div>
  );
}
