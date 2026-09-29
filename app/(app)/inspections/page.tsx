"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { GeoBadge, MineSelect } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Card, EmptyState, ErrorState, Input, LinkButton, Loading, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, humanize, outcomeLabel, outcomeTone } from "@/lib/format";
import type { Inspection, Page } from "@/lib/types";

function InspectionsInner() {
  const { can } = useSession();
  const params = useSearchParams();
  const [filters, setFilters] = useState({ mine_id: params.get("mine_id") ?? "", outcome: "", inspection_type: "", q: "" });
  const [page, setPage] = useState(1);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["inspections", filters, page],
    queryFn: () => api<Page<Inspection>>("/inspections", { query: { ...filters, page, size: 20 } }),
  });
  const upd = (k: keyof typeof filters) => (v: string) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  };
  return (
    <div>
      <PageHeader
        title="Inspections"
        subtitle="Site inspections with location, time and photos"
        actions={can("inspection:write") && (
          <LinkButton href="/inspections/new">
            <Plus className="h-4 w-4" /> New inspection
          </LinkButton>
        )}
      />
      <Card>
        <div className="filterbar grid grid-cols-1 gap-3 border-b border-line p-4 sm:grid-cols-4">
          <MineSelect allowAll value={filters.mine_id} onChange={upd("mine_id")} />
          <Select value={filters.inspection_type} onChange={(e) => upd("inspection_type")(e.target.value)} aria-label="Type">
            <option value="">All types</option>
            {["routine", "safety", "environmental", "compliance_audit", "statutory", "reinspection"].map((t) => (
              <option key={t} value={t}>{humanize(t)}</option>
            ))}
          </Select>
          <Select value={filters.outcome} onChange={(e) => upd("outcome")(e.target.value)} aria-label="Outcome">
            <option value="">All outcomes</option>
            {["compliant", "minor_issues", "non_compliant", "pending"].map((o) => (
              <option key={o} value={o}>{outcomeLabel[o]}</option>
            ))}
          </Select>
          <Input placeholder="Search title or notes…" value={filters.q} onChange={(e) => upd("q")(e.target.value)} />
        </div>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <EmptyState icon={<ClipboardList className="h-6 w-6" />} title="No inspections found" />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Inspection</Th>
                  <Th>Mine</Th>
                  <Th>Inspector</Th>
                  <Th>Date</Th>
                  <Th>Location</Th>
                  <Th>Outcome</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id} className="hover:bg-fg/5/60">
                    <Td>
                      <Link href={`/inspections/${i.id}`} className="block font-medium hover:text-copper-400">
                        {i.title}
                      </Link>
                      <span className="text-xs text-muted">
                        INS-{i.number} · {humanize(i.inspection_type)} · via {i.source}
                      </span>
                    </Td>
                    <Td>{i.mine.name}</Td>
                    <Td>{i.inspector.full_name}</Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(i.inspected_at)}</Td>
                    <Td><GeoBadge verified={i.geo_verified} distance={i.distance_from_mine_km} /></Td>
                    <Td><Badge tone={outcomeTone[i.outcome]}>{outcomeLabel[i.outcome]}</Badge></Td>
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

export default function InspectionsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <InspectionsInner />
    </Suspense>
  );
}
