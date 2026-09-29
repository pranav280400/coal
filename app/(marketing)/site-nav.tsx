"use client";

import { ArrowRight, Check, ChevronDown, Globe, Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Logo } from "@/components/brand";
import { Magnetic } from "@/components/fx";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/components/ui";
import { useI18n, type Lang } from "@/lib/i18n";

export const LINKS = [
  { id: "home", label: "Home" },
  { id: "workflow", label: "Platform" },
  { id: "features", label: "Features" },
  { id: "roles", label: "Use Cases" },
  { id: "about", label: "About Us" },
  { id: "contact", label: "Resources" },
];

/** Tracks which section is under the nav so its link carries the underline. */
function useActiveSection(): string {
  const [active, setActive] = useState("home");
  useEffect(() => {
    const els = LINKS.map((l) => document.getElementById(l.id)).filter(Boolean) as HTMLElement[];
    const io = new IntersectionObserver(
      (entries) => {
        const hit = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (hit) setActive(hit.target.id);
      },
      { rootMargin: "-35% 0px -55% 0px", threshold: [0, 0.25, 0.5] },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return active;
}

function useScrolled(): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return scrolled;
}

const LANGS: { value: Lang; short: string; name: string }[] = [
  { value: "en", short: "ENG", name: "English" },
  { value: "hi", short: "हिं", name: "हिन्दी" },
];

/** Globe + "ENG" dropdown, as on the approved design. */
function LangMenu() {
  const { lang, setLang, t } = useI18n();
  const [open, setOpen] = useState(false);
  const current = LANGS.find((l) => l.value === lang) ?? LANGS[0];
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t("Language")}
        className="inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-ink transition hover:bg-fg/5"
      >
        <Globe className="h-[18px] w-[18px]" />
        {current.short}
        <ChevronDown className={cn("h-3.5 w-3.5 transition", open && "rotate-180")} />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.ul
              role="listbox"
              initial={{ opacity: 0, y: -6, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.97 }}
              transition={{ duration: 0.15 }}
              className="glass absolute right-0 z-50 mt-2 w-40 origin-top-right rounded-2xl p-1.5 shadow-[0_24px_50px_-20px_rgb(0_0_0/0.5)]"
            >
              {LANGS.map((l) => (
                <li key={l.value}>
                  <button
                    role="option"
                    aria-selected={l.value === lang}
                    lang={l.value}
                    onClick={() => {
                      setLang(l.value);
                      setOpen(false);
                    }}
                    className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm text-ink transition hover:bg-fg/5"
                  >
                    {l.name}
                    {l.value === lang && <Check className="h-4 w-4 text-copper-500" />}
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

export function SiteNav() {
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  const active = useActiveSection();
  const scrolled = useScrolled();

  return (
    <header className={cn("fixed inset-x-0 top-0 z-40 transition-all duration-500", scrolled && "glass border-x-0 border-t-0 shadow-[0_12px_40px_-24px_rgb(0_0_0/0.5)]")}>
      <div className={cn("mx-auto flex max-w-[1500px] items-center gap-4 px-5 transition-all duration-500 sm:px-8 lg:px-14", scrolled ? "h-[72px]" : "h-[92px]")}>
        {/* Ministry | Lumen */}
        <div className="flex shrink-0 items-center gap-4 xl:gap-5">
          <div className="hidden items-center gap-3 md:flex">
            <Image src="/images/emblem.png" alt="State Emblem of India" width={30} height={46} className="h-11 w-auto dark:invert" priority />
            <div className="leading-tight">
              <p className="text-[15px] font-bold text-ink">Ministry of Coal</p>
              <p className="text-xs text-muted">Government of India</p>
            </div>
          </div>
          <span className="hidden h-10 w-px bg-line-strong md:block" />
          <Link href="/" aria-label="Lumen home" className="flex items-center gap-3">
            <Logo size="md" />
            <span className="hidden text-[11px] leading-tight whitespace-nowrap text-muted 2xl:block">{t("AI for Compliant Mines")}</span>
          </Link>
        </div>

        <nav className="mx-auto hidden items-center gap-1 lg:flex" aria-label="Primary">
          {LINKS.map((l) => (
            <a
              key={l.id}
              href={`#${l.id}`}
              className={cn("relative px-2.5 py-2 text-[14px] font-medium whitespace-nowrap transition-colors xl:px-3 2xl:px-4 2xl:text-[15px]", active === l.id ? "text-ink" : "text-steel-600 hover:text-ink")}
            >
              {t(l.label)}
              {active === l.id && (
                <motion.span
                  layoutId="nav-underline"
                  className="absolute inset-x-2.5 -bottom-0.5 h-[2px] rounded-full bg-copper-500 xl:inset-x-3 2xl:inset-x-4"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              )}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5 lg:ml-0">
          <div className="hidden sm:block">
            <LangMenu />
          </div>
          <ThemeToggle className="ring-0" />
          <Magnetic strength={6} className="ml-2 hidden sm:inline-block">
            <Link
              href="/login"
              className="group inline-flex h-12 items-center gap-2 rounded-full bg-gradient-to-b from-copper-500 to-copper-700 px-7 text-[15px] font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_12px_30px_-12px_rgb(176_100_47/0.9)] transition hover:brightness-110"
            >
              {t("Login")}
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
            </Link>
          </Magnetic>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? t("Close menu") : t("Open menu")}
            aria-expanded={open}
            className="grid h-10 w-10 place-items-center rounded-full text-ink ring-1 ring-fg/10 lg:hidden"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="glass mx-3 mb-3 rounded-3xl p-3 lg:hidden"
          >
            <nav className="flex flex-col" aria-label="Primary mobile">
              {LINKS.map((l, i) => (
                <motion.a
                  key={l.id}
                  href={`#${l.id}`}
                  onClick={() => setOpen(false)}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.04 * i }}
                  className={cn("rounded-2xl px-4 py-3 text-lg font-semibold active:bg-fg/5", active === l.id ? "text-copper-500" : "text-ink")}
                >
                  {t(l.label)}
                </motion.a>
              ))}
            </nav>
            <div className="mt-2 flex items-center gap-2 border-t border-line px-1 pt-3">
              <Link href="/login" className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-full bg-copper-600 text-sm font-semibold text-white">
                {t("Login")} <ArrowRight className="h-4 w-4" />
              </Link>
              <LangMenu />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
