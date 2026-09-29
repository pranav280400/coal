"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, HardHat, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useSession } from "@/components/session";
import { Badge, Button, Card, cn, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { bandTone, humanize } from "@/lib/format";
import type { Contractor, ContractorDetail, Page, Subsidiary } from "@/lib/types";

const STATUS_TONE = { active: "ok", pending_verification: "warn", suspended: "bad", blacklisted: "bad" } as const;

function scoreTone(score: number): string {
  return score >= 80 ? "text-ok" : score >= 60 ? "text-warn" : "text-bad";
}

function RegisterForm({ onDone }: { onDone: (id: string) => void }) {
  const { me, isGlobal } = useSession();
  const qc = useQueryClient();
  const { data: subs = [] } = useQuery({ queryKey: ["subsidiaries"], queryFn: () => api<Subsidiary[]>("/subsidiaries"), enabled: isGlobal });
  const [f, setF] = useState({ subsidiary_id: "", name: "", registration_no: "", gstin: "", pan: "", category: "", contact_person: "", contact_email: "", contact_phone: "", address: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }));
  const save = useMutation({
    mutationFn: () =>
      api<ContractorDetail>("/contractors", {
        body: {
          ...f,
          subsidiary_id: f.subsidiary_id || null,
          gstin: f.gstin.toUpperCase() || null,
          pan: f.pan.toUpperCase() || null,
          contact_email: f.contact_email || null,
          contact_phone: f.contact_phone || null,
          address: f.address || null,
        },
      }),
    onSuccess: (c) => {
      toast.success("Contractor registered — pending verification");
      void qc.invalidateQueries({ queryKey: ["contractors"] });
      onDone(c.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
      {isGlobal && (
        <Field label="Subsidiary" required>
          <Select value={f.subsidiary_id} onChange={set("subsidiary_id")} required>
            <option value="">Select…</option>
            {subs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
      )}
      {!isGlobal && me.subsidiary_name && <p className="text-sm text-muted">Registering under {me.subsidiary_name}</p>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Legal name" required><Input value={f.name} onChange={set("name")} required /></Field>
        <Field label="CLRA licence / registration no." required><Input value={f.registration_no} onChange={set("registration_no")} required /></Field>
        <Field label="GSTIN" hint="15 characters"><Input value={f.gstin} onChange={set("gstin")} maxLength={15} /></Field>
        <Field label="PAN" hint="Stored encrypted"><Input value={f.pan} onChange={set("pan")} maxLength={10} /></Field>
        <Field label="Work category" required><Input value={f.category} onChange={set("category")} required placeholder="Overburden removal, transport…" /></Field>
        <Field label="Contact person" required><Input value={f.contact_person} onChange={set("contact_person")} required /></Field>
        <Field label="Contact email"><Input type="email" value={f.contact_email} onChange={set("contact_email")} /></Field>
        <Field label="Contact phone"><Input value={f.contact_phone} onChange={set("contact_phone")} placeholder="+91…" /></Field>
      </div>
      <Field label="Address"><Input value={f.address} onChange={set("address")} /></Field>
      <div className="flex justify-end">
        <Button type="submit" loading={save.isPending}>Register contractor</Button>
      </div>
    </form>
  );
}

function ContractorsInner() {
  const { can } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(params.get("new") === "1");
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["contractors", status, q, page],
    queryFn: () => api<Page<Contractor>>("/contractors", { query: { status, q, page, size: 20 } }),
  });
  return (
    <div>
      <PageHeader
        title="Contractor Registry"
        subtitle="Contractors working at your mines, their licences and how well they comply"
        actions={can("contractor:write") && <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Register contractor</Button>}
      />
      <Card>
        <div className="filterbar grid grid-cols-1 gap-3 border-b border-line p-4 sm:grid-cols-3">
          <Input placeholder="Search name or licence no…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Status">
            <option value="">All statuses</option>
            {Object.keys(STATUS_TONE).map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
          <EmptyState icon={<HardHat className="h-6 w-6" />} title="No contractors" />
        ) : (
          <>
            <Table>
              <thead>
                <tr><Th>Contractor</Th><Th>Category</Th><Th>Contracts</Th><Th>Compliance score</Th><Th>Risk</Th><Th>Status</Th></tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id} className="hover:bg-fg/5/60">
                    <Td>
                      <Link href={`/contractors/${c.id}`} className="flex items-center gap-1.5 font-medium hover:text-copper-400">
                        {c.name} {c.verified && <BadgeCheck className="h-4 w-4 text-ok" aria-label="Verified" />}
                      </Link>
                      <span className="text-xs text-muted">{c.registration_no}</span>
                    </Td>
                    <Td>{c.category}</Td>
                    <Td>{c.active_contracts} active</Td>
                    <Td><span className={cn("text-lg font-bold tabular-nums", scoreTone(c.compliance_score))}>{c.compliance_score.toFixed(0)}</span><span className="text-xs text-muted"> / 100</span></Td>
                    <Td>{c.risk_score !== null ? <Badge tone={bandTone[c.risk_score >= 80 ? "critical" : c.risk_score >= 60 ? "high" : c.risk_score >= 35 ? "moderate" : "low"]}>{c.risk_score.toFixed(0)}</Badge> : "—"}</Td>
                    <Td><Badge tone={STATUS_TONE[c.status]}>{humanize(c.status)}</Badge></Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} size={20} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={open} onClose={() => { setOpen(false); if (params.get("new")) router.replace("/contractors"); }} title="Register contractor" wide>
        <RegisterForm onDone={(id) => { setOpen(false); router.push(`/contractors/${id}`); }} />
      </Modal>
    </div>
  );
}

export default function ContractorsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ContractorsInner />
    </Suspense>
  );
}
