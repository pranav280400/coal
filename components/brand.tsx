import Image from "next/image";
import cn from "clsx";

/*
 * Lumen brand: the triangle mark (coal faces, copper peak, a sunlit L) and the LUMEN
 * wordmark with the copper U and E-bar. Source art: public/images/login/lumen f logo.png,
 * cut into public/brand/* (full-size cuts in public/brand/source/) (light-theme originals plus dark-theme
 * versions with light lettering and lifted faces). The light / dark pair swaps with the
 * theme via the `dark:` variant; `light` forces the dark-background version.
 */

// Pre-sized to 4x the largest display height (sharp on retina, a few KB); served as-is.
const MARK = { w: 239, h: 176 };
const WORD = { w: 575, h: 96 };

function Themed({ src, alt, w, h, className, onDark }: { src: string; alt: string; w: number; h: number; className?: string; onDark?: boolean }) {
  const dark = src.replace(/\.webp$/, "-dark.webp");
  if (onDark) return <Image src={dark} alt={alt} width={w} height={h} unoptimized className={cn("w-auto", className)} />;
  return (
    <>
      <Image src={src} alt={alt} width={w} height={h} unoptimized className={cn("w-auto dark:hidden", className)} />
      <Image src={dark} alt="" aria-hidden width={w} height={h} unoptimized className={cn("hidden w-auto dark:block", className)} />
    </>
  );
}

/** The triangle mark on its own (favicon-style uses, collapsed sidebar). */
export function LumenMark({ className, light }: { className?: string; light?: boolean }) {
  return <Themed src="/brand/mark.webp" alt="Lumen" w={MARK.w} h={MARK.h} className={className} onDark={light} />;
}

/** The LUMEN wordmark, lettering as drawn in the brand art. */
export function LumenWord({ light, className }: { light?: boolean; className?: string }) {
  return <Themed src="/brand/wordmark.webp" alt="LUMEN" w={WORD.w} h={WORD.h} className={className} onDark={light} />;
}

export function Logo({
  light,
  compact,
  className,
  size = "md",
}: {
  light?: boolean;
  compact?: boolean;
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const mark = size === "lg" ? "h-11" : size === "sm" ? "h-8" : "h-9";
  const word = size === "lg" ? "h-[22px]" : size === "sm" ? "h-[15px]" : "h-[18px]";
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LumenMark className={mark} light={light} />
      {!compact && <LumenWord light={light} className={word} />}
    </div>
  );
}

export function MinistryMark({ light, className }: { light?: boolean; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Image
        src="/images/emblem.png"
        alt="State Emblem of India"
        width={26}
        height={40}
        className="h-9 w-auto dark:invert"
      />
      <div className="leading-tight">
        <p className={cn("text-sm font-semibold", light ? "text-white" : "text-ink")}>Ministry of Coal</p>
        <p className={cn("text-[11px]", light ? "text-white/70" : "text-muted")}>Government of India</p>
      </div>
    </div>
  );
}
