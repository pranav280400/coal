"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { ApiError } from "@/lib/api";
import { I18nProvider } from "@/lib/i18n";

function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => undefined);
  }, []);
  return null;
}

/**
 * Page zoom is off (see the viewport in app/layout.tsx). iOS Safari ignores user-scalable=no,
 * so pinch gestures are stopped here too; maps keep their own pinch-to-zoom.
 */
function NoZoom() {
  useEffect(() => {
    const onGesture = (e: Event) => e.preventDefault();
    const onTouch = (e: TouchEvent) => {
      if (e.touches.length > 1 && !(e.target as Element | null)?.closest?.(".leaflet-container")) e.preventDefault();
    };
    document.addEventListener("gesturestart", onGesture);
    document.addEventListener("gesturechange", onGesture);
    document.addEventListener("touchmove", onTouch, { passive: false });
    return () => {
      document.removeEventListener("gesturestart", onGesture);
      document.removeEventListener("gesturechange", onGesture);
      document.removeEventListener("touchmove", onTouch);
    };
  }, []);
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
          },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      {/* Every animation honours the operating system's "reduce motion" setting. */}
      <MotionConfig reducedMotion="user">
        <I18nProvider>{children}</I18nProvider>
      </MotionConfig>
      <Toaster position="top-right" richColors closeButton />
      <ServiceWorkerRegistrar />
      <NoZoom />
    </QueryClientProvider>
  );
}
