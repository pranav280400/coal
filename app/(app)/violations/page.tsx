"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Plus, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { MineSelect } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Card, EmptyState, ErrorState, Input, LinkButton, Loading, PageHeader, Pagination, Select, Table, Tabs, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, humanize, severityTone, violationTone } from "@/lib/format";
import type { Page, Violation } from "@/lib/types";

type View = "open" | "all" | "closed";

function ViolationsInner() {
  const { can } = useSession();
  const params = useSearchParams();
  const [view, setView] = useState<View>(params.get("open_only") === "false" ? "all" : "open");
  const [filters, setFilters] = useState({
    mine_id: params.get("mine_id") ?? "",
    severity: params.get("severity") ?? "",
    category: "",
    kind: "",
    contractor_id: params.get("contractor_id") ?? "",
    q: "",
  });
  const [page, setPage] = useState(1);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["violations", view, filters, page],
    queryFn: () =>
      api<Page<Violation>>("/violations", {
        query: { ...filters, page, size: 20, open_only: view === "open", status: view === "closed" ? "closed" : undefined },
      }),
  });
  const upd = (k: keyof typeof filters) => (v: string) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  };
  return (
    <div>
      <PageHeader
        title="Violations & Observations"
        subtitle="Problems found at mines. Assign a fix before the deadline, or it is escalated automatically."
        actions={can("violation:write") && (
          <LinkButton href="/violations/new">
            <Plus className="h-4 w-4" /> Report violation
          </LinkButton>
        )}
      />
      <div className="mb-4">
        <Tabs<View>
          value={view}
          onChange={(v) => { setView(v); setPage(1); }}
          tabs={[{ value: "open", label: "Open" }, { value: "closed", label: "Closed" }, { value: "all", label: "All" }]}
        />
      </div>
      <Card>
        <div className="filterbar grid grid-cols-1 gap-3 border-b border-line p-4 sm:grid-cols-5">
          <MineSelect allowAll value={filters.mine_id} onChange={upd("mine_id")} />
          <Select value={filters.severity} onChange={(e) => upd("severity")(e.target.value)} aria-label="Severity">
            <option value="">All severities</option>
            {["critical", "high", "medium", "low"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
          <Select value={filters.category} onChange={(e) => upd("category")(e.target.value)} aria-label="Category">
            <option value="">All categories</option>
            {["safety", "environment", "production", "labour"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
          <Select value={filters.kind} onChange={(e) => upd("kind")(e.target.value)} aria-label="Type">
            <option value="">All types</option>
            {["violation", "safety_observation", "incident"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
          <Input placeholder="Search…" value={filters.q} onChange={(e) => upd("q")(e.target.value)} />
        </div>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <EmptyState icon={<TriangleAlert className="h-6 w-6" />} title="No violations" body="Nothing matches the current filters." />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Violation</Th>
                  <Th>Mine</Th>
                  <Th>Severity</Th>
                  <Th>Status</Th>
                  <Th>Occurred</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((v) => (
                  <tr key={v.id} className="hover:bg-fg/5/60">
                    <Td>
                      <Link href={`/violations/${v.id}`} className="block font-medium hover:text-copper-400">{v.title}</Link>
                      <span className="flex items-center gap-1 text-xs text-muted">
                        VIO-{v.number} · {humanize(v.category)} · {humanize(v.kind)}
                        {v.detected_by === "ai" && <span className="inline-flex items-center gap-0.5 text-violet"><Bot className="h-3 w-3" /> AI</span>}
                      </span>
                    </Td>
                    <Td>{v.mine.name}</Td>
                    <Td>
                      <Badge tone={severityTone[v.severity]}>{humanize(v.severity)}</Badge>
                      {!v.severity_confirmed && <span className="ml-1 text-xs text-warn">unconfirmed</span>}
                    </Td>
                    <Td>
                      <Badge tone={violationTone[v.status]}>{humanize(v.status)}</Badge>
                      {v.escalation_level > 0 && v.status !== "closed" && <Badge tone="bad" className="ml-1">L{v.escalation_level}</Badge>}
                    </Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(v.occurred_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} size={20} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}

export default function ViolationsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ViolationsInner />
    </Suspense>
  );
}
