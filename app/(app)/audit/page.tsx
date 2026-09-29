"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ScrollText, ShieldCheck, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, humanize } from "@/lib/format";
import type { AuditEntry, Page } from "@/lib/types";

interface VerifyResult {
  valid: boolean;
  checked: number;
  first_invalid_id: number | null;
  head_hash: string | null;
  verified_at: string;
}

const ENTITIES = ["violation", "corrective_action", "inspection", "compliance_item", "contractor", "contract", "document", "user", "mine", "report", "anomaly", "attendance"];

function Diff({ before, after }: { before: Record<string, unknown> | null; after: Record<string, unknown> | null }) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  if (!keys.length) return <p className="text-sm text-muted">No field changes recorded.</p>;
  return (
    <Table>
      <thead><tr><Th>Field</Th><Th>Before</Th><Th>After</Th></tr></thead>
      <tbody>
        {keys.map((k) => {
          const b = JSON.stringify(before?.[k] ?? null);
          const a = JSON.stringify(after?.[k] ?? null);
          return (
            <tr key={k} className={b !== a ? "bg-warn-soft/40" : ""}>
              <Td className="font-medium">{k}</Td>
              <Td className="font-mono text-xs break-all">{b}</Td>
              <Td className="font-mono text-xs break-all">{a}</Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

export default function AuditPage() {
  const [filters, setFilters] = useState({ entity_type: "", action: "", entity_id: "" });
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AuditEntry | null>(null);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["audit", filters, page],
    queryFn: () => api<Page<AuditEntry>>("/audit", { query: { ...filters, page, size: 30 } }),
  });
  const verify = useMutation({
    mutationFn: () => api<VerifyResult>("/audit/verify"),
    onSuccess: (r) =>
      r.valid ? toast.success(`Audit chain intact — ${r.checked} entries verified`) : toast.error(`Tampering detected at entry #${r.first_invalid_id}`),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div>
      <PageHeader
        title="Audit Logs"
        subtitle="A permanent record of every change — who did what, and when. Entries cannot be edited or deleted."
        actions={<Button onClick={() => verify.mutate()} loading={verify.isPending}><ShieldCheck className="h-4 w-4" /> Check records are untampered</Button>}
      />
      {verify.data && (
        <div className={`mb-4 flex items-center gap-3 rounded-2xl px-5 py-3 text-sm ${verify.data.valid ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad"}`}>
          {verify.data.valid ? <ShieldCheck className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}
          <span>
            {verify.data.valid ? `All ${verify.data.checked} records checked — nothing has been altered.` : `Record #${verify.data.first_invalid_id} has been altered. The ${verify.data.checked} records before it are intact.`}{" "}
            ({fmtDateTime(verify.data.verified_at)})
          </span>
        </div>
      )}
      <Card>
        <div className="filterbar grid grid-cols-1 gap-3 border-b border-line p-4 sm:grid-cols-3">
          <Select value={filters.entity_type} onChange={(e) => { setFilters((f) => ({ ...f, entity_type: e.target.value })); setPage(1); }} aria-label="Entity type">
            <option value="">All record types</option>
            {ENTITIES.map((e) => <option key={e} value={e}>{humanize(e)}</option>)}
          </Select>
          <Input placeholder="Filter by action, e.g. violation" value={filters.action} onChange={(e) => { setFilters((f) => ({ ...f, action: e.target.value })); setPage(1); }} />
          <Input placeholder="Record ID" value={filters.entity_id} onChange={(e) => { setFilters((f) => ({ ...f, entity_id: e.target.value })); setPage(1); }} />
        </div>
        {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
          <EmptyState icon={<ScrollText className="h-6 w-6" />} title="No audit entries" />
        ) : (
          <>
            <Table>
              <thead><tr><Th>#</Th><Th>Time</Th><Th>Action</Th><Th>Record</Th><Th>Done by</Th></tr></thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id} className="cursor-pointer hover:bg-fg/5/60" onClick={() => setSelected(e)}>
                    <Td className="tabular-nums text-muted">{e.id}</Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(e.ts)}</Td>
                    <Td><Badge tone="neutral">{humanize(e.action.replace(".", " "))}</Badge></Td>
                    <Td>{humanize(e.entity_type)} <span className="font-mono text-xs text-muted">{e.entity_id.slice(0, 8)}</span></Td>
                    <Td>{e.actor_name ?? "System"}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} size={30} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={!!selected} onClose={() => setSelected(null)} title={`Audit entry #${selected?.id}`} wide>
        {selected && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <p><span className="text-muted">Action:</span> {selected.action}</p>
              <p><span className="text-muted">Actor:</span> {selected.actor_name ?? "System"}</p>
              <p><span className="text-muted">Record:</span> {humanize(selected.entity_type)} {selected.entity_id}</p>
              <p><span className="text-muted">Time:</span> {fmtDateTime(selected.ts)}</p>
            </div>
            <div className="rounded-xl bg-canvas p-3 font-mono text-xs break-all">
              <p><span className="text-muted">prev_hash</span> {selected.prev_hash}</p>
              <p><span className="text-muted">hash&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span> {selected.hash}</p>
            </div>
            <Diff before={selected.before} after={selected.after} />
          </div>
        )}
      </Modal>
    </div>
  );
}
