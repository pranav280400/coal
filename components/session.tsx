"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { Logo } from "@/components/brand";

interface SessionValue {
  me: Me;
  can: (perm: string) => boolean;
  isGlobal: boolean;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { data, error } = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/auth/me"), staleTime: 5 * 60_000 });
  if (!data) {
    return (
      <div className="app-backdrop flex min-h-screen flex-col items-center justify-center gap-6 text-white">
        <div className="relative">
          <span aria-hidden className="absolute inset-0 -m-8 rounded-full bg-copper-500/25 blur-3xl motion-safe:animate-pulse" />
          <Logo size="lg" className="relative" />
        </div>
        {error ? (
          <p className="text-sm text-muted">Unable to load your session. Please sign in again.</p>
        ) : (
          <div className="h-0.5 w-40 overflow-hidden rounded-full bg-fg/10" role="status" aria-label="Loading">
            <div className="shimmer h-full w-full [--color-surface:transparent] [--color-raised:#e3a473]" />
          </div>
        )}
      </div>
    );
  }
  const value: SessionValue = {
    me: data,
    can: (perm) => data.permissions.includes(perm),
    isGlobal: data.role === "admin" || data.role === "regulator" || (data.role === "corporate" && !data.subsidiary_id),
  };
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
