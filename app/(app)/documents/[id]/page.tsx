"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import { use } from "react";
import { toast } from "sonner";
import { Section, Timeline } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, ErrorState, KeyValue, Loading, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtBytes, fmtDateTime, humanize, processingTone } from "@/lib/format";
import type { DocumentDetail } from "@/lib/types";

function renderValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.map(String).join("; ") || "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export default function DocumentDetailPage({ params }: PageProps<"/documents/[id]">) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { can } = useSession();
  const { data: d, error, isLoading, refetch } = useQuery({
    queryKey: ["document", id],
    queryFn: () => api<DocumentDetail>(`/documents/${id}`),
    refetchInterval: (q) => (q.state.data && ["pending", "processing"].includes(q.state.data.ocr_status) ? 4000 : false),
  });
  const reprocess = useMutation({
    mutationFn: () => api(`/documents/${id}/reprocess`, { method: "POST" }),
    onSuccess: () => { toast.success("Re-processing started"); void qc.invalidateQueries({ queryKey: ["document", id] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (isLoading) return <Loading />;
  if (error || !d) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const fields = Object.entries(d.extracted_fields ?? {}).filter(([k]) => k !== "summary");
  return (
    <div className="space-y-5">
      <PageHeader
        title={d.title}
        subtitle={`${d.filename} · ${fmtBytes(d.size_bytes)} · uploaded ${fmtDateTime(d.created_at)}`}
        actions={
          <>
            <a href={`/api/files/document/${d.id}`} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-2 rounded-xl border border-line bg-surface px-4 text-sm font-medium hover:bg-fg/5"><Download className="h-4 w-4" /> Download original</a>
            {can("document:write") && d.ocr_status !== "processing" && (
              <Button variant="ghost" onClick={() => reprocess.mutate()} loading={reprocess.isPending}><RefreshCw className="h-4 w-4" /> Re-process</Button>
            )}
          </>
        }
      />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Section title="AI extraction">
            <div className="mb-3 flex flex-wrap gap-2">
              <Badge tone={processingTone[d.ocr_status]}>{humanize(d.ocr_status)}</Badge>
              <Badge tone="neutral">{humanize(d.doc_type)}</Badge>
              {d.ocr_confidence !== null && <Badge tone="info">Text accuracy {Math.round(d.ocr_confidence * 100)}%</Badge>}
              {d.embedded_chunks > 0 && <Badge tone="ok">{d.embedded_chunks} searchable chunks</Badge>}
            </div>
            {d.error && <p className="mb-3 rounded-xl bg-warn-soft px-3 py-2 text-sm text-warn">{d.error}</p>}
            {d.summary && <p className="mb-4 text-sm">{d.summary}</p>}
            {fields.length ? <KeyValue items={fields.map(([k, v]) => ({ label: humanize(k), value: renderValue(v) }))} /> : <p className="text-sm text-muted">Structured fields appear once AI extraction completes.</p>}
          </Section>
          <Section title="Text read from the document">
            {d.ocr_text ? (
              <pre className="scroll-thin max-h-[480px] overflow-auto rounded-xl bg-canvas p-4 text-xs whitespace-pre-wrap">{d.ocr_text}</pre>
            ) : <p className="text-sm text-muted">No text extracted yet.</p>}
          </Section>
        </div>
        <div className="space-y-5">
          <Section title="Integrity">
            <p className="text-xs text-muted">SHA-256</p>
            <p className="font-mono text-xs break-all">{d.sha256}</p>
          </Section>
          <Section title="Audit trail"><Timeline entity="document" id={d.id} /></Section>
        </div>
      </div>
    </div>
  );
}
