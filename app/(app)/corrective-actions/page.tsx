"use client";

import { useQuery } from "@tanstack/react-query";
import { Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader, Pagination, Select, Table, Tabs, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { actionTone, fmtDateTime, humanize } from "@/lib/format";
import type { CorrectiveAction, Page } from "@/lib/types";

type View = "mine" | "all";

export default function CorrectiveActionsPage() {
  const [view, setView] = useState<View>("mine");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["actions", view, status, page],
    queryFn: () => api<Page<CorrectiveAction>>("/corrective-actions", { query: { mine: view === "mine", status, page, size: 20 } }),
  });
  const now = dataUpdatedAt; // reference time = when this list was fetched
  return (
    <div>
      <PageHeader title="Corrective Actions" subtitle="Fixes assigned for each violation — follow them until they are checked and closed" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs<View> value={view} onChange={(v) => { setView(v); setPage(1); }} tabs={[{ value: "mine", label: "Assigned to me" }, { value: "all", label: "All in my scope" }]} />
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="w-48" aria-label="Status">
          <option value="">All statuses</option>
          {["assigned", "in_progress", "submitted", "overdue", "rejected", "verified"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
        </Select>
      </div>
      <Card>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <EmptyState icon={<Wrench className="h-6 w-6" />} title="No corrective actions" body={view === "mine" ? "Nothing is assigned to you right now." : undefined} />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Action</Th>
                  <Th>Violation</Th>
                  <Th>Assignee</Th>
                  <Th>Deadline</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => {
                  const late = !["verified", "submitted"].includes(a.status) && new Date(a.deadline).getTime() < now;
                  return (
                    <tr key={a.id} className="hover:bg-fg/5/60">
                      <Td>
                        <Link href={`/corrective-actions/${a.id}`} className="font-medium hover:text-copper-400">{a.title}</Link>
                      </Td>
                      <Td>
                        <Link href={`/violations/${a.violation_id}`} className="text-sm hover:text-copper-400">VIO-{a.violation_number} · {a.violation_title}</Link>
                        <span className="block text-xs text-muted">{a.mine_name}</span>
                      </Td>
                      <Td>{a.assignee.full_name}</Td>
                      <Td className={late ? "font-semibold text-bad" : ""}>{fmtDateTime(a.deadline)}</Td>
                      <Td><Badge tone={actionTone[a.status]}>{humanize(a.status)}</Badge></Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <Pagination page={page} size={20} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
