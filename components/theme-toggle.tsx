"use client";

import { Moon, Sun } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import { setTheme, useTheme } from "@/lib/theme";

/** Sun / moon switch; the icon spins over and the new theme spreads out from the button. */
export function ThemeToggle({ className }: { className?: string }) {
  const theme = useTheme();
  const { t } = useI18n();
  const next = theme === "dark" ? "light" : "dark";
  const label = next === "light" ? t("Switch to light theme") : t("Switch to dark theme");
  return (
    <button
      type="button"
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setTheme(next, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
      }}
      aria-label={label}
      title={label}
      className={cn(
        "relative grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-full text-steel-600 ring-1 ring-fg/10 transition hover:bg-fg/5 hover:text-ink active:scale-95",
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ y: 14, rotate: -90, opacity: 0 }}
          animate={{ y: 0, rotate: 0, opacity: 1 }}
          exit={{ y: -14, rotate: 90, opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="grid place-items-center"
        >
          {theme === "dark" ? <Moon className="h-[18px] w-[18px]" /> : <Sun className="h-[18px] w-[18px] text-copper-500" />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
