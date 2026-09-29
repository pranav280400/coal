"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CircleCheck, Plus, RefreshCw, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { toast } from "sonner";
import { MediaGallery, Section, Timeline, UserSelect } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, ErrorState, Field, Input, KeyValue, Loading, Modal, PageHeader, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { actionTone, fmtDateTime, humanize, severityTone, violationTone } from "@/lib/format";
import type { CorrectiveAction, Page, SimilarItem, Violation } from "@/lib/types";

const SLA = { critical: "4 hours", high: "24 hours", medium: "72 hours", low: "7 days" };

export default function ViolationDetailPage({ params }: PageProps<"/violations/[id]">) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { can } = useSession();
  const [modal, setModal] = useState<"confirm" | "assign" | "close" | null>(null);
  const [severity, setSeverity] = useState("");
  const [notes, setNotes] = useState("");
  const [action, setAction] = useState({ title: "", description: "", assigned_to: "", deadline: "" });
  const [showSimilar, setShowSimilar] = useState(false);

  const { data: v, error, isLoading, refetch } = useQuery({ queryKey: ["violation", id], queryFn: () => api<Violation>(`/violations/${id}`) });
  const { data: actions } = useQuery({
    queryKey: ["actions", "violation", id],
    queryFn: () => api<Page<CorrectiveAction>>("/corrective-actions", { query: { violation_id: id, size: 50 } }),
  });
  const similar = useQuery({
    queryKey: ["similar", id],
    queryFn: () => api<SimilarItem[]>(`/violations/${id}/similar`),
    enabled: showSimilar,
    retry: false,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["violation", id] });
    void qc.invalidateQueries({ queryKey: ["actions"] });
    void qc.invalidateQueries({ queryKey: ["timeline", "violation", id] });
  };
  const classify = useMutation({
    mutationFn: () => api<Violation>(`/violations/${id}/classify`, { method: "POST" }),
    onSuccess: (res) => {
      toast.success(`AI (${res.ai_source}) suggests ${humanize(res.ai_suggested_severity)} severity`);
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const confirm = useMutation({
    mutationFn: () => api(`/violations/${id}/confirm`, { body: { severity, notes: notes || null } }),
    onSuccess: () => { toast.success("Severity confirmed"); setModal(null); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const assign = useMutation({
    mutationFn: () =>
      api("/corrective-actions", {
        body: { violation_id: id, title: action.title, description: action.description, assigned_to: action.assigned_to, deadline: new Date(action.deadline).toISOString() },
      }),
    onSuccess: () => {
      toast.success("Corrective action assigned — the assignee has been notified");
      setModal(null);
      setAction({ title: "", description: "", assigned_to: "", deadline: "" });
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const close = useMutation({
    mutationFn: () => api(`/violations/${id}/close`, { body: { notes } }),
    onSuccess: () => { toast.success("Violation closed"); setModal(null); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (isLoading) return <Loading />;
  if (error || !v) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const open = v.status !== "closed";

  return (
    <div className="space-y-5">
      <PageHeader
        title={v.title}
        subtitle={`VIO-${v.number} · ${v.mine.name} · ${fmtDateTime(v.occurred_at)}`}
        actions={
          open && (
            <>
              {can("violation:confirm") && (
                <Button variant="outline" onClick={() => { setSeverity(v.ai_suggested_severity ?? v.severity); setNotes(""); setModal("confirm"); }}>
                  <ShieldCheck className="h-4 w-4" /> Confirm severity
                </Button>
              )}
              {can("action:assign") && (
                <Button onClick={() => setModal("assign")}>
                  <Plus className="h-4 w-4" /> Assign corrective action
                </Button>
              )}
              {can("action:verify") && (
                <Button variant="ghost" onClick={() => { setNotes(""); setModal("close"); }}>
                  <CircleCheck className="h-4 w-4" /> Close
                </Button>
              )}
            </>
          )
        }
      />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Section title="Details">
            <div className="mb-4 flex flex-wrap gap-2">
              <Badge tone={severityTone[v.severity]}>{humanize(v.severity)} severity</Badge>
              {!v.severity_confirmed && <Badge tone="warn">Awaiting human confirmation</Badge>}
              <Badge tone={violationTone[v.status]}>{humanize(v.status)}</Badge>
              {v.escalation_level > 0 && open && <Badge tone="bad">Escalated · level {v.escalation_level}</Badge>}
              {v.detected_by === "ai" && <Badge tone="violet">AI-detected</Badge>}
            </div>
            <p className="text-sm whitespace-pre-line">{v.description}</p>
            <div className="mt-4">
              <KeyValue
                items={[
                  { label: "Type", value: humanize(v.kind) },
                  { label: "Category", value: humanize(v.category) },
                  { label: "Statutory reference", value: v.regulation_ref ?? "—" },
                  { label: "Fix within", value: SLA[v.severity] },
                  { label: "Inspection", value: v.inspection_id ? <Link className="text-copper-400 underline" href={`/inspections/${v.inspection_id}`}>View inspection</Link> : "—" },
                  { label: "Contractor", value: v.contractor_id ? <Link className="text-copper-400 underline" href={`/contractors/${v.contractor_id}`}>View contractor</Link> : "—" },
                  { label: "Closed", value: fmtDateTime(v.closed_at) },
                ]}
              />
            </div>
          </Section>

          <Section title={`Corrective actions (${actions?.total ?? 0})`}>
            {actions?.items.length ? (
              <ul className="divide-y divide-line">
                {actions.items.map((a) => (
                  <li key={a.id}>
                    <Link href={`/corrective-actions/${a.id}`} className="flex items-center gap-3 py-3 text-sm hover:text-copper-400">
                      <span className="flex-1">
                        <span className="block font-medium">{a.title}</span>
                        <span className="text-xs text-muted">{a.assignee.full_name} · due {fmtDateTime(a.deadline)}</span>
                      </span>
                      <Badge tone={actionTone[a.status]}>{humanize(a.status)}</Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No corrective action assigned yet. It is escalated if no fix is assigned within {SLA[v.severity]}.</p>
            )}
          </Section>

          <Section
            title="Similar past cases"
            action={
              !showSimilar && (
                <Button size="sm" variant="secondary" onClick={() => setShowSimilar(true)}>
                  <Search className="h-4 w-4" /> Find similar
                </Button>
              )
            }
          >
            {!showSimilar ? (
              <p className="text-sm text-muted">Finds past cases like this one, and what fixed them.</p>
            ) : similar.isLoading ? (
              <Loading label="Searching the knowledge base…" />
            ) : similar.error ? (
              <p className="text-sm text-bad">{errorMessage(similar.error)}</p>
            ) : similar.data?.length ? (
              <ul className="space-y-2">
                {similar.data.map((s) => (
                  <li key={`${s.source_type}-${s.source_id}`}>
                    <Link href={`/${s.source_type === "violation" ? "violations" : "inspections"}/${s.source_id}`} className="block rounded-xl border border-line p-3 hover:bg-fg/5">
                      <span className="flex items-center justify-between gap-2 text-sm font-medium">
                        {s.title}
                        <Badge tone="info">{Math.round(s.score * 100)}% match</Badge>
                      </span>
                      <span className="mt-1 block text-xs text-muted">{s.snippet}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No similar cases found.</p>
            )}
          </Section>
        </div>

        <div className="space-y-5">
          <Section
            title="AI assessment"
            action={
              can("ai:use") && open && (
                <Button size="sm" variant="ghost" onClick={() => classify.mutate()} loading={classify.isPending} title="Re-run AI classification">
                  <RefreshCw className="h-4 w-4" />
                </Button>
              )
            }
          >
            {v.ai_suggested_severity ? (
              <div className="space-y-3 text-sm">
                <div className="flex items-center gap-2">
                  <Bot className="h-5 w-5 text-violet" />
                  <Badge tone={severityTone[v.ai_suggested_severity]}>{humanize(v.ai_suggested_severity)}</Badge>
                  <span className="text-muted">{Math.round((v.ai_confidence ?? 0) * 100)}% confidence</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-canvas">
                  <div className="h-full bg-violet" style={{ width: `${Math.round((v.ai_confidence ?? 0) * 100)}%` }} />
                </div>
                {v.ai_rationale && <p className="text-muted">{v.ai_rationale}</p>}
                <p className="text-xs text-muted">
                  {v.ai_source === "llm" ? "Based on the regulations and similar past cases" : "Based on keyword rules (AI service unavailable)"}
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted">No AI assessment yet.</p>
            )}
          </Section>
          <Section title="Evidence">
            <MediaGallery entity="violation" id={v.id} />
          </Section>
          <Section title="Timeline">
            <Timeline entity="violation" id={v.id} />
          </Section>
        </div>
      </div>

      <Modal open={modal === "confirm"} onClose={() => setModal(null)} title="Confirm severity">
        <form onSubmit={(e) => { e.preventDefault(); confirm.mutate(); }} className="space-y-4">
          <p className="text-sm text-muted">AI suggested <strong>{humanize(v.ai_suggested_severity)}</strong>. Your confirmation sets the deadline for fixing it.</p>
          <Field label="Severity" required>
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              {["critical", "high", "medium", "low"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </Select>
          </Field>
          <Field label="Notes">
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setModal(null)}>Cancel</Button>
            <Button type="submit" loading={confirm.isPending}>Confirm</Button>
          </div>
        </form>
      </Modal>

      <Modal open={modal === "assign"} onClose={() => setModal(null)} title="Assign corrective action">
        <form onSubmit={(e) => { e.preventDefault(); assign.mutate(); }} className="space-y-4">
          <Field label="Action" required>
            <Input value={action.title} onChange={(e) => setAction((a) => ({ ...a, title: e.target.value }))} required minLength={3} />
          </Field>
          <Field label="Instructions">
            <Textarea value={action.description} onChange={(e) => setAction((a) => ({ ...a, description: e.target.value }))} />
          </Field>
          <Field label="Assign to" required>
            <UserSelect value={action.assigned_to} onChange={(val) => setAction((a) => ({ ...a, assigned_to: val }))} mineId={v.mine_id} />
          </Field>
          <Field label="Deadline" required>
            <Input type="datetime-local" value={action.deadline} onChange={(e) => setAction((a) => ({ ...a, deadline: e.target.value }))} required />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setModal(null)}>Cancel</Button>
            <Button type="submit" loading={assign.isPending}>Assign</Button>
          </div>
        </form>
      </Modal>

      <Modal open={modal === "close"} onClose={() => setModal(null)} title="Close violation">
        <form onSubmit={(e) => { e.preventDefault(); close.mutate(); }} className="space-y-4">
          <p className="text-sm text-muted">High and critical violations can only be closed after their corrective actions are verified.</p>
          <Field label="Closure notes" required>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} required minLength={3} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setModal(null)}>Cancel</Button>
            <Button type="submit" loading={close.isPending}>Close violation</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
