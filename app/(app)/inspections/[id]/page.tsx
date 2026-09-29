"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ClipboardCheck, Sparkles, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { toast } from "sonner";
import { GeoBadge, MediaGallery, Section, Timeline, useMines } from "@/components/common";
import { MineMap } from "@/components/map";
import { useSession } from "@/components/session";
import { Badge, Button, ErrorState, Field, KeyValue, LinkButton, Loading, Modal, PageHeader, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, humanize, outcomeLabel, outcomeTone, severityTone, violationTone } from "@/lib/format";
import type { InspectionDetail, MinePoint } from "@/lib/types";

export default function InspectionDetailPage({ params }: PageProps<"/inspections/[id]">) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { can } = useSession();
  const [review, setReview] = useState(false);
  const [outcome, setOutcome] = useState("non_compliant");
  const [reviewNotes, setReviewNotes] = useState("");
  const [lang, setLang] = useState("en");
  const { data: mines = [] } = useMines();
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["inspection", id],
    queryFn: () => api<InspectionDetail>(`/inspections/${id}`),
    // Poll briefly while the FieldIngestAgent workflow enriches the record.
    refetchInterval: (q) => (q.state.data && !q.state.data.ai_summary && q.state.data.status !== "reviewed" ? 8000 : false),
  });
  const summarize = useMutation({
    mutationFn: () => api<{ summary: string }>(`/ai/inspections/${id}/summarize`, { method: "POST", query: { language: lang } }),
    onSuccess: (res) => {
      if (lang === "en") void qc.invalidateQueries({ queryKey: ["inspection", id] });
      else toast.info(res.summary, { duration: 20000 });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const doReview = useMutation({
    mutationFn: () => api(`/inspections/${id}/review`, { body: { outcome, notes: reviewNotes || null } }),
    onSuccess: () => {
      toast.success("Inspection reviewed");
      setReview(false);
      void qc.invalidateQueries({ queryKey: ["inspection", id] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  const mine = mines.find((m) => m.id === data.mine_id);
  const minePoint: MinePoint[] = mine
    ? [{ id: mine.id, code: mine.code, name: mine.name, subsidiary_code: mine.subsidiary.code, latitude: mine.latitude, longitude: mine.longitude,
        status: data.outcome === "non_compliant" ? "non_compliant" : data.outcome === "minor_issues" ? "minor_issues" : "compliant",
        open_violations: 0, critical_violations: 0, overdue_compliance: 0, compliance_rate: 0, risk_score: mine.risk_score }]
    : [];
  const findings = data.ai_findings;

  return (
    <div className="space-y-5">
      <PageHeader
        title={data.title}
        subtitle={`INS-${data.number} · ${data.mine.name} · ${humanize(data.inspection_type)} · ${fmtDateTime(data.inspected_at)}`}
        actions={
          <>
            {can("violation:write") && (
              <LinkButton href={`/violations/new?inspection_id=${data.id}&mine_id=${data.mine_id}`} variant="outline">
                <TriangleAlert className="h-4 w-4" /> Report violation
              </LinkButton>
            )}
            {can("violation:confirm") && data.status !== "reviewed" && (
              <Button onClick={() => setReview(true)}>
                <ClipboardCheck className="h-4 w-4" /> Review
              </Button>
            )}
          </>
        }
      />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Section title="Summary">
            <div className="mb-4 flex flex-wrap gap-2">
              <Badge tone={outcomeTone[data.outcome]}>{outcomeLabel[data.outcome]}</Badge>
              <Badge tone={data.status === "reviewed" ? "ok" : "info"}>{humanize(data.status)}</Badge>
              <GeoBadge verified={data.geo_verified} distance={data.distance_from_mine_km} />
              <Badge tone="neutral">via {data.source}</Badge>
            </div>
            <KeyValue
              items={[
                { label: "Inspector", value: data.inspector.full_name },
                { label: "Mine", value: data.mine.name },
                { label: "Coordinates", value: data.latitude !== null ? `${data.latitude?.toFixed(5)}, ${data.longitude?.toFixed(5)} (±${data.geo_accuracy_m ?? "?"} m)` : "Not captured" },
                { label: "Recorded", value: fmtDateTime(data.created_at) },
              ]}
            />
            {data.notes && <p className="mt-4 text-sm whitespace-pre-line">{data.notes}</p>}
          </Section>

          <Section
            title="AI analysis"
            action={
              can("ai:use") && (
                <div className="flex items-center gap-2">
                  <Select value={lang} onChange={(e) => setLang(e.target.value)} className="h-8 w-28 text-xs" aria-label="Language">
                    <option value="en">English</option>
                    <option value="hi">हिन्दी</option>
                    <option value="or">ଓଡ଼ିଆ</option>
                    <option value="bn">বাংলা</option>
                  </Select>
                  <Button size="sm" variant="secondary" onClick={() => summarize.mutate()} loading={summarize.isPending}>
                    <Sparkles className="h-4 w-4" /> {data.ai_summary ? "Regenerate" : "Summarise"}
                  </Button>
                </div>
              )
            }
          >
            {data.ai_summary ? (
              <div className="space-y-4 text-sm">
                <p>{data.ai_summary}</p>
                {findings?.hazards?.length ? (
                  <div>
                    <p className="mb-2 font-semibold">Hazards identified</p>
                    <ul className="space-y-1.5">
                      {findings.hazards.map((h, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Badge tone={severityTone[h.severity] ?? "neutral"}>{humanize(h.severity)}</Badge>
                          <span>{h.description}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {findings?.recommended_actions?.length ? (
                  <div>
                    <p className="mb-2 font-semibold">Recommended actions</p>
                    <ol className="list-decimal space-y-1 pl-5">
                      {findings.recommended_actions.map((a, i) => <li key={i}>{a}</li>)}
                    </ol>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted">
                After submission the system reads attachments, summarises the findings and flags hazards automatically. You can also create a summary now.
              </p>
            )}
          </Section>

          <Section title={`Checklist (${data.checklist.filter((c) => !c.passed).length} deficiencies)`}>
            <ul className="divide-y divide-line">
              {data.checklist.map((c, i) => (
                <li key={i} className="flex items-start gap-3 py-2.5 text-sm">
                  {c.passed ? <Check className="mt-0.5 h-4 w-4 text-ok" /> : <X className="mt-0.5 h-4 w-4 text-bad" />}
                  <span className="flex-1">
                    {c.item}
                    {c.note && <span className="block text-xs text-muted">{c.note}</span>}
                  </span>
                </li>
              ))}
              {!data.checklist.length && <li className="py-3 text-sm text-muted">No checklist recorded.</li>}
            </ul>
          </Section>

          <Section title={`Violations (${data.violations.length})`}>
            {data.violations.length ? (
              <ul className="divide-y divide-line">
                {data.violations.map((v) => (
                  <li key={v.id}>
                    <Link href={`/violations/${v.id}`} className="flex items-center gap-3 py-2.5 text-sm hover:text-copper-400">
                      <span className="flex-1">
                        <span className="font-medium">{v.title}</span>
                        <span className="block text-xs text-muted">VIO-{v.number} · {v.detected_by === "ai" ? "AI-detected" : "Reported"}</span>
                      </span>
                      <Badge tone={severityTone[v.severity]}>{humanize(v.severity)}</Badge>
                      <Badge tone={violationTone[v.status]}>{humanize(v.status)}</Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No violations linked to this inspection.</p>
            )}
          </Section>
        </div>

        <div className="space-y-5">
          <Section title="Location">
            <div className="h-64 overflow-hidden rounded-xl">
              <MineMap
                mines={minePoint}
                boundaries={mine?.boundary_geojson ? [{ id: mine.id, coordinates: mine.boundary_geojson.coordinates[0] }] : []}
                extra={data.latitude !== null && data.longitude !== null ? [{ id: data.id, latitude: data.latitude, longitude: data.longitude, color: data.geo_verified ? "#3b6fd8" : "#dc3a3a", label: "Inspection geo-tag", radius: 7 }] : []}
              />
            </div>
          </Section>
          <Section title="Photo evidence">
            <MediaGallery entity="inspection" id={data.id} />
          </Section>
          <Section title="Audit trail">
            <Timeline entity="inspection" id={data.id} />
          </Section>
        </div>
      </div>

      <Modal open={review} onClose={() => setReview(false)} title="Review inspection">
        <form onSubmit={(e) => { e.preventDefault(); doReview.mutate(); }} className="space-y-4">
          <Field label="Confirmed outcome" required>
            <Select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
              <option value="compliant">Compliant</option>
              <option value="minor_issues">Minor issues</option>
              <option value="non_compliant">Non-compliant</option>
            </Select>
          </Field>
          <Field label="Review notes">
            <Textarea value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setReview(false)}>Cancel</Button>
            <Button type="submit" loading={doReview.isPending}>Confirm review</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
