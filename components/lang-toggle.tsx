"use client";

import { cn } from "@/components/ui";
import { useI18n, type Lang } from "@/lib/i18n";

const OPTIONS: { value: Lang; label: string; title: string }[] = [
  { value: "en", label: "EN", title: "English" },
  { value: "hi", label: "हि", title: "हिन्दी" },
];

/** EN / हिन्दी switch. `onChange` lets signed-in pages also save the choice to the profile. */
export function LangToggle({
  className,
  size = "md",
  tone = "dark",
  onChange,
}: {
  className?: string;
  size?: "sm" | "md";
  tone?: "dark" | "light";
  onChange?: (lang: Lang) => void;
}) {
  const { lang, setLang, t } = useI18n();
  return (
    <div
      className={cn("flex items-center rounded-full p-1 ring-1 ring-fg/10", tone === "dark" ? "bg-fg/[0.04]" : "bg-fg/10", className)}
      role="group"
      aria-label={t("Language")}
    >
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.title}
          lang={o.value}
          onClick={() => {
            setLang(o.value);
            onChange?.(o.value);
          }}
          aria-pressed={lang === o.value}
          className={cn(
            "rounded-full font-semibold tracking-wide transition",
            size === "sm" ? "h-7 w-9 text-xs" : "h-9 w-12 text-sm",
            lang === o.value ? "bg-copper-600 text-white shadow-[0_4px_14px_-6px_rgb(212_136_78/0.9)]" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
