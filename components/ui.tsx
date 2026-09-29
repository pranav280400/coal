"use client";

import clsx from "clsx";
import { ChevronLeft, ChevronRight, LoaderCircle, X } from "lucide-react";
import Link from "next/link";
import {
  Children,
  cloneElement,
  forwardRef,
  isValidElement,
  useEffect,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import type { Tone } from "@/lib/format";
import { motion } from "motion/react";
import { translateNode, useI18n } from "@/lib/i18n";

export const cn = clsx;

// ------------------------------------------------------------------ button
type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";

// Primary actions glow faintly copper and lift a step on hover; the rest stay quiet.
const PRIMARY =
  "bg-gradient-to-b from-copper-500 to-copper-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_8px_24px_-10px_rgb(212_136_78/0.8)] hover:from-copper-600 hover:to-copper-700 active:shadow-none";
const SECONDARY = "bg-copper-500/12 text-copper-300 ring-1 ring-inset ring-copper-500/20 hover:bg-copper-500/20";
const OUTLINE = "border border-line-strong bg-fg/[0.02] text-ink hover:border-copper-500/40 hover:bg-fg/5";
const GHOST = "text-muted hover:bg-fg/5 hover:text-ink";

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg"; loading?: boolean }
>(function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...props }, ref) {
  const { t } = useI18n();
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition duration-200 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-copper-400 focus-visible:ring-offset-2 ring-offset-canvas disabled:cursor-not-allowed disabled:opacity-60",
        size === "sm" && "h-8 px-3 text-sm max-sm:h-10",
        size === "md" && "h-10 px-4 text-sm max-sm:h-11 max-sm:text-[15px]",
        size === "lg" && "h-12 px-6 text-base",
        variant === "primary" && PRIMARY,
        variant === "secondary" && SECONDARY,
        variant === "outline" && OUTLINE,
        variant === "ghost" && GHOST,
        variant === "danger" && "bg-bad text-white shadow-[0_8px_24px_-10px_rgb(242_95_76/0.7)] hover:bg-bad/90",
        className,
      )}
      {...props}
    >
      {loading && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
      {translateNode(children, t)}
    </button>
  );
});

export function LinkButton({
  href,
  children,
  variant = "primary",
  className,
}: {
  href: string;
  children: ReactNode;
  variant?: Variant;
  className?: string;
}) {
  const { t } = useI18n();
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition duration-200 active:scale-[0.97] max-sm:h-11 max-sm:text-[15px]",
        variant === "primary" && PRIMARY,
        variant === "secondary" && SECONDARY,
        variant === "outline" && OUTLINE,
        variant === "ghost" && GHOST,
        className,
      )}
    >
      {translateNode(children, t)}
    </Link>
  );
}

// -------------------------------------------------------------------- card
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("min-w-0 rounded-2xl border border-fg/[0.06] bg-surface bg-[linear-gradient(180deg,rgb(255_255_255/0.025),transparent_120px)] shadow-card", className)}>{children}</section>;
}

export function CardHeader({
  title,
  action,
  subtitle,
}: {
  title: ReactNode;
  action?: ReactNode;
  subtitle?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4 pb-3 sm:px-5">
      <div>
        <h2 className="text-base font-bold tracking-tight text-ink">{translateNode(title, t)}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{translateNode(subtitle, t)}</p>}
      </div>
      {action}
    </div>
  );
}

// ------------------------------------------------------------------- badge
const toneClasses: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  info: "bg-info-soft text-info",
  violet: "bg-violet-soft text-violet",
  neutral: "bg-fg/5 text-steel-600",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  const { t } = useI18n();
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ring-fg/[0.06]",
        toneClasses[tone],
        className,
      )}
    >
      {translateNode(children, t)}
    </span>
  );
}

// ------------------------------------------------------------------ inputs
const fieldBase =
  "w-full rounded-xl border border-line-strong bg-raised px-3.5 text-sm text-ink placeholder:text-steel-400 transition hover:border-steel-300 focus:border-copper-500 focus:outline-none focus:ring-4 focus:ring-copper-500/15 disabled:opacity-60 max-sm:text-base";

/** Filter controls given a fixed width on desktop go full width on phones. */
function fullOnPhone(className?: string): string | false {
  return !!className && /(^|\s)w-\d/.test(className) && "max-sm:w-full!";
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref,
) {
  return <input ref={ref} className={cn(fieldBase, "h-10 max-sm:h-12", className, fullOnPhone(className))} {...props} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(fieldBase, "min-h-24 py-2.5", className)} {...props} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...props },
  ref,
) {
  return (
    <select ref={ref} className={cn(fieldBase, "h-10 pr-8 max-sm:h-12", className, fullOnPhone(className))} {...props}>
      {children}
    </select>
  );
});

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
  required,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  htmlFor?: string;
  required?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">
        {t(label)}
        {required && <span className="text-bad"> *</span>}
      </label>
      {children}
      {error ? <p className="text-xs text-bad">{error}</p> : hint ? <p className="text-xs text-muted">{t(hint)}</p> : null}
    </div>
  );
}

// ------------------------------------------------------------------ states
export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={cn("h-5 w-5 animate-spin text-copper-600", className)} aria-label="Loading" />;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-muted" role="status">
      <Spinner /> {t(label)}
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon?: ReactNode; title: string; body?: string; action?: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-4 rounded-2xl bg-copper-500/10 p-3.5 text-copper-400 ring-1 ring-copper-500/20 shadow-[0_0_40px_-8px_rgb(212_136_78/0.5)]">{icon}</div>}
      <p className="font-semibold text-ink">{t(title)}</p>
      {body && <p className="mt-1 max-w-sm text-sm text-muted">{t(body)}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="m-4 rounded-xl border border-bad/30 bg-bad-soft px-4 py-3 text-sm text-bad" role="alert">
      {message}
      {onRetry && (
        <button className="ml-3 font-semibold underline" onClick={onRetry}>
          {t("Retry")}
        </button>
      )}
    </div>
  );
}

// ------------------------------------------------------------ page chrome
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="font-display text-[26px] leading-tight font-bold tracking-[-0.03em] text-ink sm:text-[34px]">{t(title)}</h1>
        {subtitle && <p className="mt-1 text-[15px] leading-relaxed text-muted">{t(subtitle)}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2 max-sm:w-full max-sm:[&>*]:flex-1 max-sm:[&>*]:basis-full">{actions}</div>}
    </div>
  );
}

export function Pagination({
  page,
  size,
  total,
  onPage,
}: {
  page: number;
  size: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (total <= size) return null;
  return (
    <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm text-muted">
      <span>
        {(page - 1) * size + 1}–{Math.min(page * size, total)} of {total}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="px-2">
          {page} / {pages}
        </span>
        <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  return "";
}

type Props = { children?: ReactNode };

/** Copies each column heading onto its cells so phones can show rows as labelled cards. */
function labelRows(children: ReactNode): ReactNode {
  let labels: string[] = [];
  const parts = Children.toArray(children);
  for (const part of parts) {
    if (isValidElement<Props>(part) && part.type === "thead") {
      const row = Children.toArray(part.props.children)[0];
      if (isValidElement<Props>(row)) {
        labels = Children.toArray(row.props.children).map((th) => (isValidElement<Props>(th) ? textOf(th.props.children) : ""));
      }
    }
  }
  if (!labels.length) return children;
  return parts.map((part) => {
    if (!isValidElement<Props>(part) || part.type !== "tbody") return part;
    return cloneElement(part, {
      children: Children.map(part.props.children, (tr) => {
        if (!isValidElement<Props>(tr) || tr.type !== "tr") return tr;
        let i = 0;
        return cloneElement(tr, {
          children: Children.map(tr.props.children, (td) =>
            isValidElement(td) && td.type === Td ? cloneElement(td as ReactElement<{ label?: string }>, { label: labels[i++] ?? "" }) : td,
          ),
        });
      }),
    });
  });
}

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="rtable scroll-thin overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">{labelRows(children)}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  const { t } = useI18n();
  return (
    <th className={cn("border-b border-line bg-fg/[0.02] px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted", className)}>
      {translateNode(children, t)}
    </th>
  );
}

export function Td({ children, className, label }: { children?: ReactNode; className?: string; label?: string }) {
  const { t } = useI18n();
  return (
    <td data-label={label ? t(label) : ""} className={cn("border-b border-line/70 px-5 py-3.5 align-middle", className)}>
      {children}
    </td>
  );
}

// ------------------------------------------------------------------- modal
export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  const { t } = useI18n();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="animate-overlay-in fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-md sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t(title)}
        className={cn(
          "animate-sheet-in sm:animate-dialog-in scroll-thin max-h-[92dvh] w-full overflow-y-auto rounded-t-3xl border border-fg/10 bg-raised pb-[env(safe-area-inset-bottom)] shadow-[0_30px_80px_-20px_rgb(0_0_0/0.8)] sm:rounded-2xl sm:pb-0",
          wide ? "sm:max-w-3xl" : "sm:max-w-lg",
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-raised/90 px-5 py-4 backdrop-blur">
          <span className="absolute top-2 left-1/2 h-1.5 w-10 -translate-x-1/2 rounded-full bg-steel-200 sm:hidden" aria-hidden />
          <h2 className="text-lg font-bold">{t(title)}</h2>
          <button onClick={onClose} className="grid h-10 w-10 place-items-center rounded-full text-muted hover:bg-fg/5" aria-label={t("Close")}>
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- tabs
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const { t: tr } = useI18n();
  const group = useId();
  return (
    <div className="scroll-thin flex gap-1 overflow-x-auto rounded-xl border border-line bg-surface p-1" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={t.value === value}
          onClick={() => onChange(t.value)}
          className={cn(
            "relative whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-semibold transition",
            t.value === value ? "text-white" : "text-muted hover:text-ink",
          )}
        >
          {t.value === value && (
            <motion.span
              layoutId={`tab-pill-${group}`}
              className="absolute inset-0 rounded-lg bg-gradient-to-b from-copper-500 to-copper-600 shadow-[0_6px_18px_-8px_rgb(212_136_78/0.9)]"
              transition={{ type: "spring", stiffness: 500, damping: 38 }}
            />
          )}
          <span className="relative">
            {tr(t.label)}
            {t.count !== undefined && <span className="ml-1.5 opacity-70">{t.count}</span>}
          </span>
        </button>
      ))}
    </div>
  );
}

export function KeyValue({ items }: { items: { label: string; value: ReactNode }[] }) {
  const { t } = useI18n();
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map((it) => (
        <div key={it.label}>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted">{t(it.label)}</dt>
          <dd className="mt-0.5 text-sm text-ink">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
