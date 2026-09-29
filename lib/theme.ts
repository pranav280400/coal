"use client";

import { useSyncExternalStore } from "react";

/**
 * Light / dark theme. The choice lives on <html data-theme> (set before first paint by
 * THEME_SCRIPT in the root layout) and in localStorage; with no saved choice the OS
 * setting decides.
 */

export type Theme = "light" | "dark";
import { THEME_KEY as KEY } from "@/lib/theme-script";


function read(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function subscribe(cb: () => void): () => void {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => mo.disconnect();
}

type ViewTransitionDoc = Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } };

/**
 * Switches theme. With `origin` (the toggle's centre) and View Transitions support, the new
 * theme spreads out from the button as a circle; otherwise colours cross-fade briefly.
 */
export function setTheme(next: Theme, origin?: { x: number; y: number }) {
  const root = document.documentElement;
  const apply = () => {
    root.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* private mode: the choice just won't persist */
    }
  };
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const doc = document as ViewTransitionDoc;
  if (origin && doc.startViewTransition && !reduce) {
    const r = Math.hypot(Math.max(origin.x, innerWidth - origin.x), Math.max(origin.y, innerHeight - origin.y));
    const vt = doc.startViewTransition(apply);
    void vt.ready.then(() => {
      root.animate(
        { clipPath: [`circle(0px at ${origin.x}px ${origin.y}px)`, `circle(${r}px at ${origin.x}px ${origin.y}px)`] },
        { duration: 560, easing: "cubic-bezier(0.22, 1, 0.36, 1)", pseudoElement: "::view-transition-new(root)" },
      );
    });
    return;
  }
  root.classList.add("theme-switching");
  apply();
  window.setTimeout(() => root.classList.remove("theme-switching"), 400);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, read, () => "dark");
}
