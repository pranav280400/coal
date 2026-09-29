"use client";

// English / Hindi UI switch. Strings are keyed by their English text, so a missing
// translation simply falls back to English instead of showing a key.

import { Children, createContext, isValidElement, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { HI } from "@/lib/i18n-hi";

export type Lang = "en" | "hi";
const STORAGE_KEY = "lumen-lang";

type Vars = Record<string, string | number>;
interface I18nValue {
  lang: Lang;
  setLang: (lang: Lang, opts?: { persist?: boolean }) => void;
  /** True once the viewer has picked a language on this device (overrides the profile default). */
  chosen: boolean;
  t: (text: string, vars?: Vars) => string;
}

function interpolate(text: string, vars?: Vars): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

const I18nContext = createContext<I18nValue>({
  lang: "en",
  setLang: () => undefined,
  chosen: false,
  t: (text, vars) => interpolate(text, vars),
});

// The chosen language lives in localStorage; useSyncExternalStore keeps every
// consumer (and other tabs) in step without setting state inside an effect.
const listeners = new Set<() => void>();

function readStored(): Lang | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === "en" || v === "hi" ? v : null;
  } catch {
    return null;
  }
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const stored = useSyncExternalStore(subscribe, readStored, () => null);
  // A non-persisted default (e.g. from the user's profile) used until they pick one here.
  const [fallback, setFallback] = useState<Lang | null>(null);
  const lang: Lang = stored ?? fallback ?? "en";

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang, opts?: { persist?: boolean }) => {
    if (opts?.persist === false) {
      setFallback(next);
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      setFallback(next); // storage blocked: still switch for this session
    }
    listeners.forEach((l) => l());
  }, []);

  const t = useCallback(
    (text: string, vars?: Vars) => interpolate(lang === "hi" ? (HI[text] ?? text) : text, vars),
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, chosen: stored !== null, t }), [lang, setLang, stored, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}

/** Translate plain-string children, keeping surrounding whitespace and leaving elements alone. */
export function translateNode(node: ReactNode, t: I18nValue["t"]): ReactNode {
  if (typeof node === "string") {
    const trimmed = node.trim();
    if (!trimmed) return node;
    const lead = node.slice(0, node.indexOf(trimmed));
    const tail = node.slice(node.indexOf(trimmed) + trimmed.length);
    return `${lead}${t(trimmed)}${tail}`;
  }
  if (Array.isArray(node)) {
    return Children.map(node, (child) => (isValidElement(child) ? child : translateNode(child, t)));
  }
  return node;
}

/** Inline translation for server components, e.g. `<T>Get started</T>`. */
export function T({ children, vars }: { children: string; vars?: Vars }) {
  const { t } = useI18n();
  return <>{t(children, vars)}</>;
}
