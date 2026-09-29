"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { MineMap } from "@/components/map";
import { Card, cn, ErrorState, Input, Loading, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { riskColor } from "@/lib/format";
import type { Inspection, MinePoint, Page } from "@/lib/types";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "compliant", label: "Compliant", dot: "bg-ok" },
  { value: "minor_issues", label: "Minor Issues", dot: "bg-warn" },
  { value: "non_compliant", label: "Non-Compliant", dot: "bg-bad" },
] as const;

function MapInner() {
  const params = useSearchParams();
  const [focus, setFocus] = useState<string | null>(params.get("mine"));
  const [status, setStatus] = useState<string>("all");
  const [q, setQ] = useState("");
  const [showInspections, setShowInspections] = useState(false);
  const { data: mines, error, isLoading, refetch } = useQuery({ queryKey: ["mines", "map"], queryFn: () => api<MinePoint[]>("/mines/map") });
  const { data: inspections } = useQuery({
    queryKey: ["inspections", "map"],
    queryFn: () => api<Page<Inspection>>("/inspections", { query: { size: 200 } }),
    enabled: showInspections,
  });
  const filtered = useMemo(
    () => (mines ?? []).filter((m) => (status === "all" || m.status === status) && (!q || `${m.name} ${m.code}`.toLowerCase().includes(q.toLowerCase()))),
    [mines, status, q],
  );
  if (isLoading) return <Loading />;
  if (error || !mines) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const extra = showInspections
    ? (inspections?.items ?? [])
        .filter((i) => i.latitude !== null && i.longitude !== null)
        .map((i) => ({ id: i.id, latitude: i.latitude!, longitude: i.longitude!, color: i.geo_verified ? "#3b6fd8" : "#dc3a3a", label: `INS-${i.number} ${i.title}`, href: `/inspections/${i.id}`, radius: 4 }))
    : [];
  return (
    <div>
      <PageHeader title="Maps & Locations" subtitle="Where each mine is and how it is doing" />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[320px_1fr]">
        <Card className="flex max-h-[70vh] flex-col">
          <div className="space-y-3 border-b border-line p-4">
            <Input placeholder="Filter mines…" value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="flex flex-wrap gap-1.5">
              {FILTERS.map((f) => (
                <button key={f.value} onClick={() => setStatus(f.value)}
                  className={cn("flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium", status === f.value ? "bg-copper-600 text-white" : "bg-canvas")}>
                  {"dot" in f && <span className={cn("h-2 w-2 rounded-full", f.dot)} />} {f.label}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={showInspections} onChange={(e) => setShowInspections(e.target.checked)} className="accent-copper-700" />
              Show inspection geo-tags
            </label>
          </div>
          <ul className="scroll-thin flex-1 divide-y divide-line overflow-y-auto">
            {filtered.map((m) => (
              <li key={m.id}>
                <button onClick={() => setFocus(m.id)} className={cn("w-full px-4 py-3 text-left hover:bg-fg/5", focus === m.id && "bg-copper-50")}>
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-semibold">{m.name}</span>
                    <span className="rounded-md px-1.5 text-xs font-bold text-white" style={{ background: riskColor(m.risk_score) }}>{m.risk_score?.toFixed(0) ?? "—"}</span>
                  </span>
                  <span className="text-xs text-muted">{m.code} · {m.compliance_rate}% compliant · {m.open_violations} open</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="h-[70vh] overflow-hidden">
          <MineMap mines={filtered} extra={extra} focusId={focus} />
        </Card>
      </div>
    </div>
  );
}

export default function MapPage() {
  return (
    <Suspense fallback={<Loading />}>
      <MapInner />
    </Suspense>
  );
}
