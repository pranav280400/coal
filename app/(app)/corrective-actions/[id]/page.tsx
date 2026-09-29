"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Play, Send, Upload, X } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { toast } from "sonner";
import { MediaGallery, Section, Timeline } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, ErrorState, Field, Input, KeyValue, Loading, PageHeader, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { actionTone, fmtDateTime, humanize } from "@/lib/format";
import type { CorrectiveAction } from "@/lib/types";

export default function ActionDetailPage({ params }: PageProps<"/corrective-actions/[id]">) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { me, can } = useSession();
  const [notes, setNotes] = useState("");
  const [verifyNotes, setVerifyNotes] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const { data: a, error, isLoading, refetch } = useQuery({ queryKey: ["action", id], queryFn: () => api<CorrectiveAction>(`/corrective-actions/${id}`) });
  const done = () => {
    void qc.invalidateQueries({ queryKey: ["action", id] });
    void qc.invalidateQueries({ queryKey: ["actions"] });
    void qc.invalidateQueries({ queryKey: ["media", "corrective_action", id] });
    void qc.invalidateQueries({ queryKey: ["timeline", "corrective_action", id] });
  };
  const start = useMutation({
    mutationFn: () => api(`/corrective-actions/${id}/start`, { method: "POST" }),
    onSuccess: () => { toast.success("Marked in progress"); done(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const submit = useMutation({
    mutationFn: async () => {
      for (const f of Array.from(files ?? [])) {
        const form = new FormData();
        form.append("file", f);
        form.append("captured_at", new Date().toISOString());
        await api(`/media/corrective_action/${id}`, { method: "POST", form });
      }
      return api(`/corrective-actions/${id}/submit`, { body: { completion_notes: notes } });
    },
    onSuccess: () => { toast.success("Submitted for verification"); setNotes(""); setFiles(null); done(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const verify = useMutation({
    mutationFn: (decision: "approve" | "reject") => api(`/corrective-actions/${id}/verify`, { body: { decision, notes: verifyNotes } }),
    onSuccess: (_, decision) => { toast.success(decision === "approve" ? "Verified" : "Returned to assignee"); setVerifyNotes(""); done(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (isLoading) return <Loading />;
  if (error || !a) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const isAssignee = a.assignee.id === me.id;
  const canWork = (isAssignee || me.role === "admin" || me.role === "mine_official") && can("action:execute");
  const executable = ["assigned", "in_progress", "rejected", "overdue"].includes(a.status);

  return (
    <div className="space-y-5">
      <PageHeader title={a.title} subtitle={`VIO-${a.violation_number} · ${a.mine_name ?? ""}`} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Section title="Action">
            <div className="mb-4 flex gap-2">
              <Badge tone={actionTone[a.status]}>{humanize(a.status)}</Badge>
            </div>
            <KeyValue
              items={[
                { label: "Violation", value: <Link href={`/violations/${a.violation_id}`} className="text-copper-400 underline">{a.violation_title}</Link> },
                { label: "Assignee", value: a.assignee.full_name },
                { label: "Deadline", value: fmtDateTime(a.deadline) },
                { label: "Submitted", value: fmtDateTime(a.submitted_at) },
                { label: "Verified", value: fmtDateTime(a.verified_at) },
                { label: "Verification notes", value: a.verification_notes ?? "—" },
              ]}
            />
            {a.description && <p className="mt-4 text-sm whitespace-pre-line">{a.description}</p>}
            {a.completion_notes && (
              <div className="mt-4 rounded-xl bg-canvas p-3 text-sm">
                <p className="mb-1 text-xs font-semibold text-muted uppercase">Completion report</p>
                {a.completion_notes}
              </div>
            )}
          </Section>

          {canWork && executable && (
            <Section title="Update progress">
              <div className="space-y-4">
                {a.status !== "in_progress" && (
                  <Button variant="outline" onClick={() => start.mutate()} loading={start.isPending}>
                    <Play className="h-4 w-4" /> Start work
                  </Button>
                )}
                <Field label="Completion report" required>
                  <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What was done, materials, who verified on site…" />
                </Field>
                <Field label="Evidence photos / documents">
                  <Input type="file" multiple accept="image/*,application/pdf" capture="environment" onChange={(e) => setFiles(e.target.files)} className="py-2" />
                </Field>
                <Button onClick={() => submit.mutate()} loading={submit.isPending} disabled={notes.trim().length < 5}>
                  <Send className="h-4 w-4" /> Submit for verification
                </Button>
              </div>
            </Section>
          )}

          {a.status === "submitted" && can("action:verify") && (
            <Section title="Verification">
              {isAssignee ? (
                <p className="text-sm text-muted">Segregation of duties: another official must verify your own submission.</p>
              ) : (
                <div className="space-y-4">
                  <Field label="Verification notes" required>
                    <Textarea value={verifyNotes} onChange={(e) => setVerifyNotes(e.target.value)} placeholder="Site verification findings…" />
                  </Field>
                  <div className="flex gap-2">
                    <Button onClick={() => verify.mutate("approve")} loading={verify.isPending} disabled={verifyNotes.trim().length < 3}>
                      <CircleCheck className="h-4 w-4" /> Approve
                    </Button>
                    <Button variant="danger" onClick={() => verify.mutate("reject")} loading={verify.isPending} disabled={verifyNotes.trim().length < 3}>
                      <X className="h-4 w-4" /> Reject
                    </Button>
                  </div>
                </div>
              )}
            </Section>
          )}
        </div>
        <div className="space-y-5">
          <Section title="Evidence" action={<Upload className="h-4 w-4 text-muted" />}>
            <MediaGallery entity="corrective_action" id={a.id} />
          </Section>
          <Section title="Timeline">
            <Timeline entity="corrective_action" id={a.id} />
          </Section>
        </div>
      </div>
    </div>
  );
}
