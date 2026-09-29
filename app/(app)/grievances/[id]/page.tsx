"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Play, RotateCcw, Star, UserPlus, X } from "lucide-react";
import { use, useState } from "react";
import { toast } from "sonner";
import { Section, Timeline } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, cn, ErrorState, Field, KeyValue, Loading, PageHeader, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, grievanceTone, humanize, roleLabel, severityTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Grievance, Page, User } from "@/lib/types";

const ACTIVE = ["open", "assigned", "in_progress"];

function AssignForm({ g, onDone }: { g: Grievance; onDone: () => void }) {
  const { t } = useI18n();
  const [assignee, setAssignee] = useState(g.assignee?.id ?? "");
  const [priority, setPriority] = useState(g.priority);
  const { data: users = [] } = useQuery({
    queryKey: ["users", "grievance-owners"],
    queryFn: () => api<Page<User>>("/users", { query: { size: 200, status: "active" } }).then((p) => p.items),
  });
  // Owners: officials of this mine, corporate staff and administrators — never the person who raised it.
  const owners = users.filter(
    (u) =>
      (u.role === "corporate" || u.role === "admin" || (u.role === "mine_official" && u.mine_id === g.mine_id)) &&
      u.id !== g.raiser?.id,
  );
  const assign = useMutation({
    mutationFn: () => api(`/grievances/${g.id}/assign`, { body: { assignee_id: assignee, priority } }),
    onSuccess: () => { toast.success(t("Assign owner")); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_160px_auto] sm:items-end">
      <Field label="Assign to">
        <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          <option value="">{t("Select a person…")}</option>
          {owners.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name} — {t(roleLabel[u.role] ?? humanize(u.role))}
              {u.mine ? ` (${u.mine.code})` : ""}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Priority">
        <Select value={priority} onChange={(e) => setPriority(e.target.value as Grievance["priority"])}>
          {["low", "medium", "high", "critical"].map((p) => <option key={p} value={p}>{t(humanize(p))}</option>)}
        </Select>
      </Field>
      <Button onClick={() => assign.mutate()} loading={assign.isPending} disabled={!assignee}>
        <UserPlus className="h-4 w-4" /> Assign
      </Button>
    </div>
  );
}

function Stars({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1" role="radiogroup">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} / 5`}
          onClick={() => onChange(n)}
          className="rounded-lg p-1 hover:bg-copper-500/10"
        >
          <Star className={cn("h-7 w-7", n <= value ? "fill-copper-500 text-copper-500" : "text-steel-300")} />
        </button>
      ))}
    </div>
  );
}

export default function GrievanceDetailPage({ params }: PageProps<"/grievances/[id]">) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { me } = useSession();
  const { t } = useI18n();
  const [resolution, setResolution] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [reopenReason, setReopenReason] = useState("");
  const { data: g, error, isLoading, refetch, dataUpdatedAt } = useQuery({ queryKey: ["grievance", id], queryFn: () => api<Grievance>(`/grievances/${id}`) });
  const done = () => {
    void qc.invalidateQueries({ queryKey: ["grievance", id] });
    void qc.invalidateQueries({ queryKey: ["grievances"] });
    void qc.invalidateQueries({ queryKey: ["timeline", "grievance", id] });
  };
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api(`/grievances/${id}/${path}`, { method: "POST", body }),
    onSuccess: (_, v) => {
      toast.success(t({ start: "Start work", resolve: "Mark resolved", reject: "Reject grievance", close: "Confirm & close", reopen: "Reopen grievance" }[v.path] ?? "Save"));
      setResolution(""); setRejectReason(""); setComment(""); setReopenReason("");
      done();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (isLoading) return <Loading />;
  if (error || !g) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const active = ACTIVE.includes(g.status);
  const isAssignee = g.assignee?.id === me.id;
  const late = active && new Date(g.due_at).getTime() < dataUpdatedAt;
  const canWork = active && !g.is_mine && (g.can_manage || isAssignee);

  return (
    <div className="space-y-5">
      <PageHeader title={`GRV-${g.number} · ${g.subject}`} subtitle={g.mine.name} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Section title="Grievance">
            <div className="mb-4 flex flex-wrap gap-2">
              <Badge tone={grievanceTone[g.status]}>{humanize(g.status)}</Badge>
              <Badge tone={severityTone[g.priority]}>{humanize(g.priority)}</Badge>
              <Badge tone="neutral">{humanize(g.category)}</Badge>
              {g.is_anonymous && <Badge tone="violet">Anonymous</Badge>}
              {g.escalation_level > 0 && active && <Badge tone="bad">{`${t("Escalation level")} ${g.escalation_level}`}</Badge>}
            </div>
            <KeyValue
              items={[
                { label: "Raised by", value: g.raiser?.full_name ?? <span className="italic text-muted">{t("Anonymous")}</span> },
                { label: "Assignee", value: g.assignee?.full_name ?? "—" },
                { label: "Raised", value: fmtDateTime(g.created_at) },
                { label: "Resolve by", value: <span className={late ? "font-semibold text-bad" : ""}>{fmtDateTime(g.due_at)}</span> },
                { label: "Resolved", value: fmtDateTime(g.resolved_at) },
                { label: "Closed", value: fmtDateTime(g.closed_at) },
                ...(g.satisfaction ? [{ label: "Satisfaction", value: `${g.satisfaction} / 5` }] : []),
                ...(g.reopen_count ? [{ label: "Reopen", value: `${g.reopen_count}×` }] : []),
              ]}
            />
            <p className="mt-4 whitespace-pre-line text-sm">{g.description}</p>
            {g.resolution_notes && (
              <div className="mt-4 rounded-xl bg-canvas p-3 text-sm">
                <p className="mb-1 text-xs font-semibold text-muted uppercase">{t(g.status === "rejected" ? "Reason" : "Resolution")}</p>
                {g.resolution_notes}
              </div>
            )}
          </Section>

          {canWork && (
            <Section title="Update progress">
              <div className="space-y-5">
                {g.can_manage && <AssignForm g={g} onDone={done} />}
                {(g.status === "open" || g.status === "assigned") && (
                  <Button variant="outline" onClick={() => act.mutate({ path: "start" })} loading={act.isPending}>
                    <Play className="h-4 w-4" /> Start work
                  </Button>
                )}
                <div className="space-y-3 border-t border-line pt-4">
                  <Field label="Resolution notes" required>
                    <Textarea value={resolution} onChange={(e) => setResolution(e.target.value)} rows={3} />
                  </Field>
                  <Button onClick={() => act.mutate({ path: "resolve", body: { resolution_notes: resolution } })} loading={act.isPending} disabled={resolution.trim().length < 10}>
                    <CircleCheck className="h-4 w-4" /> Mark resolved
                  </Button>
                </div>
                {g.can_manage && (
                  <div className="space-y-3 border-t border-line pt-4">
                    <Field label="Reason">
                      <Textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={2} />
                    </Field>
                    <Button variant="danger" onClick={() => act.mutate({ path: "reject", body: { reason: rejectReason } })} loading={act.isPending} disabled={rejectReason.trim().length < 10}>
                      <X className="h-4 w-4" /> Reject grievance
                    </Button>
                  </div>
                )}
              </div>
            </Section>
          )}

          {g.is_mine && g.status === "resolved" && (
            <Section title="Confirm & close">
              <p className="mb-3 text-sm text-muted">{t("Your grievance was resolved. Confirm it, or reopen it if the problem remains.")}</p>
              <Field label="How satisfied are you with the resolution?">
                <Stars value={rating} onChange={setRating} />
              </Field>
              <div className="mt-3">
                <Field label="Notes">
                  <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} />
                </Field>
              </div>
              <Button className="mt-3" onClick={() => act.mutate({ path: "close", body: { satisfaction: rating, comment: comment || null } })} loading={act.isPending} disabled={!rating}>
                <CircleCheck className="h-4 w-4" /> Confirm & close
              </Button>
            </Section>
          )}

          {g.is_mine && (g.status === "resolved" || g.status === "rejected") && (
            <Section title="Reopen grievance">
              <Field label="Reason" required>
                <Textarea value={reopenReason} onChange={(e) => setReopenReason(e.target.value)} rows={2} />
              </Field>
              <Button variant="outline" className="mt-3" onClick={() => act.mutate({ path: "reopen", body: { reason: reopenReason } })} loading={act.isPending} disabled={reopenReason.trim().length < 10}>
                <RotateCcw className="h-4 w-4" /> Reopen
              </Button>
            </Section>
          )}
        </div>
        <div className="space-y-5">
          <Section title="Timeline">
            <Timeline entity="grievance" id={g.id} />
          </Section>
        </div>
      </div>
    </div>
  );
}
