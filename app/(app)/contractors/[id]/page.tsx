"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Plus } from "lucide-react";
import Link from "next/link";
import { use, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { MineSelect, Section, Timeline } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, cn, ErrorState, Field, Input, KeyValue, Loading, Modal, PageHeader, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtINR, humanize, severityTone, violationTone } from "@/lib/format";
import type { ContractorDetail, Page, Violation } from "@/lib/types";

export default function ContractorDetailPage({ params }: PageProps<"/contractors/[id]">) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { can } = useSession();
  const [open, setOpen] = useState(false);
  const [contract, setContract] = useState({ mine_id: "", work_order_no: "", title: "", value_inr: "", start_date: "", end_date: "", workforce_count: "0" });
  const { data: c, error, isLoading, refetch } = useQuery({ queryKey: ["contractor", id], queryFn: () => api<ContractorDetail>(`/contractors/${id}`) });
  const { data: violations } = useQuery({
    queryKey: ["violations", "contractor", id],
    queryFn: () => api<Page<Violation>>("/violations", { query: { contractor_id: id, size: 10 } }),
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["contractor", id] });
  const verify = useMutation({
    mutationFn: () => api(`/contractors/${id}/verify`, { method: "POST" }),
    onSuccess: () => { toast.success("Contractor verified"); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const setStatus = useMutation({
    mutationFn: (status: string) => api(`/contractors/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => { toast.success("Status updated"); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const addContract = useMutation({
    mutationFn: () => api(`/contractors/${id}/contracts`, { body: { ...contract, value_inr: contract.value_inr, workforce_count: Number(contract.workforce_count) } }),
    onSuccess: () => { toast.success("Contract added"); setOpen(false); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (isLoading) return <Loading />;
  if (error || !c) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const set = (k: keyof typeof contract) => (e: { target: { value: string } }) => setContract((s) => ({ ...s, [k]: e.target.value }));

  return (
    <div className="space-y-5">
      <PageHeader
        title={c.name}
        subtitle={`${c.registration_no} · ${c.category}`}
        actions={
          <>
            {can("contractor:verify") && !c.verified && (
              <Button onClick={() => verify.mutate()} loading={verify.isPending}><BadgeCheck className="h-4 w-4" /> Verify</Button>
            )}
            {can("contractor:verify") && (
              <Select value={c.status} onChange={(e) => setStatus.mutate(e.target.value)} className="w-52" aria-label="Contractor status">
                {["pending_verification", "active", "suspended", "blacklisted"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
              </Select>
            )}
          </>
        }
      />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Section title="Profile">
            <KeyValue
              items={[
                { label: "Status", value: <Badge tone={c.status === "active" ? "ok" : c.status === "pending_verification" ? "warn" : "bad"}>{humanize(c.status)}</Badge> },
                { label: "Verified", value: c.verified ? "Yes" : "No" },
                { label: "GSTIN", value: c.gstin ?? "—" },
                { label: "PAN", value: c.pan_masked ?? "—" },
                { label: "Contact", value: `${c.contact_person}${c.contact_phone ? ` · ${c.contact_phone}` : ""}` },
                { label: "Email", value: c.contact_email ?? "—" },
                { label: "Address", value: c.address ?? "—" },
              ]}
            />
          </Section>
          <Section
            title={`Contracts (${c.contracts.length})`}
            action={can("contractor:write") && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Add contract</Button>}
          >
            {c.contracts.length ? (
              <Table>
                <thead><tr><Th>Work order</Th><Th>Mine</Th><Th>Value</Th><Th>Period</Th><Th>Workforce</Th><Th>Status</Th></tr></thead>
                <tbody>
                  {c.contracts.map((k) => (
                    <tr key={k.id}>
                      <Td><span className="font-medium">{k.work_order_no}</span><span className="block text-xs text-muted">{k.title}</span></Td>
                      <Td>{k.mine.name}</Td>
                      <Td>{fmtINR(k.value_inr)}</Td>
                      <Td className="whitespace-nowrap">{fmtDate(k.start_date)} – {fmtDate(k.end_date)}</Td>
                      <Td>{k.workforce_count}</Td>
                      <Td><Badge tone={k.status === "active" ? "ok" : "neutral"}>{humanize(k.status)}</Badge></Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : <p className="text-sm text-muted">No contracts on record.</p>}
          </Section>
          <Section title={`Violations (${c.total_violations}, ${c.open_violations} open)`}>
            {violations?.items.length ? (
              <ul className="divide-y divide-line">
                {violations.items.map((v) => (
                  <li key={v.id}>
                    <Link href={`/violations/${v.id}`} className="flex items-center gap-3 py-2.5 text-sm hover:text-copper-400">
                      <span className="flex-1">{v.title}<span className="block text-xs text-muted">{v.mine.name} · {fmtDate(v.occurred_at)}</span></span>
                      <Badge tone={severityTone[v.severity]}>{humanize(v.severity)}</Badge>
                      <Badge tone={violationTone[v.status]}>{humanize(v.status)}</Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">Clean record.</p>}
          </Section>
        </div>
        <div className="space-y-5">
          <Section title="Compliance score">
            <p className={cn("text-5xl font-bold tabular-nums", c.compliance_score >= 80 ? "text-ok" : c.compliance_score >= 60 ? "text-warn" : "text-bad")}>
              {c.compliance_score.toFixed(0)}<span className="text-lg text-muted"> / 100</span>
            </p>
            <p className="mt-2 text-sm text-muted">Penalised for recent high/critical violations and overdue corrective actions; recomputed daily by the analytics engine.</p>
            {c.risk_score !== null && <p className="mt-3 text-sm">Risk score: <strong>{c.risk_score.toFixed(0)}</strong></p>}
          </Section>
          <Section title="Audit trail"><Timeline entity="contractor" id={c.id} /></Section>
        </div>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Add contract / work order">
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); addContract.mutate(); }} className="space-y-4">
          <Field label="Mine" required><MineSelect value={contract.mine_id} onChange={(v) => setContract((s) => ({ ...s, mine_id: v }))} required /></Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Work order no." required><Input value={contract.work_order_no} onChange={set("work_order_no")} required /></Field>
            <Field label="Value (₹)" required><Input type="number" min="0" step="0.01" value={contract.value_inr} onChange={set("value_inr")} required /></Field>
          </div>
          <Field label="Scope" required><Input value={contract.title} onChange={set("title")} required /></Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Start" required><Input type="date" value={contract.start_date} onChange={set("start_date")} required /></Field>
            <Field label="End" required><Input type="date" value={contract.end_date} onChange={set("end_date")} required /></Field>
            <Field label="Workforce"><Input type="number" min="0" value={contract.workforce_count} onChange={set("workforce_count")} /></Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={addContract.isPending}>Add contract</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
