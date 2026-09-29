"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChartColumn, Download, FileSpreadsheet, FileText, Plus, RefreshCw } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { MineSelect } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, Card, CardHeader, cn, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Select, Table, Tabs, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { bandTone, fmtDate, fmtDateTime, fromNow, humanize, processingTone } from "@/lib/format";
import type { Anomaly, Page, Report, RiskEntry, Subsidiary } from "@/lib/types";

type Tab = "reports" | "risk" | "anomalies" | "trends";

function ReportsTab() {
  const qc = useQueryClient();
  const { can, isGlobal, me } = useSession();
  const params = useSearchParams();
  // The dashboard's "Generate Report" button links here with the chosen period.
  const [open, setOpen] = useState(() => params.get("new") === "1" && can("report:generate"));
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["reports"],
    queryFn: () => api<Page<Report>>("/reports", { query: { size: 50 } }),
    refetchInterval: (q) => (q.state.data?.items.some((r) => r.status === "pending" || r.status === "processing") ? 5000 : false),
  });
  const { data: subs = [] } = useQuery({ queryKey: ["subsidiaries"], queryFn: () => api<Subsidiary[]>("/subsidiaries") });
  const today = new Date();
  const lastMonthEnd = new Date(today.getFullYear(), today.getMonth(), 0);
  const lastMonthStart = new Date(lastMonthEnd.getFullYear(), lastMonthEnd.getMonth(), 1);
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const [form, setForm] = useState({
    scope: me.role === "mine_official" ? "mine" : isGlobal ? "national" : "subsidiary",
    scope_id: me.role === "mine_official" ? me.mine_id ?? "" : me.subsidiary_id ?? "",
    period_start: params.get("start") ?? iso(lastMonthStart),
    period_end: params.get("end") ?? iso(lastMonthEnd),
  });
  const create = useMutation({
    mutationFn: () => api<Report>("/reports", { body: { ...form, scope_id: form.scope === "national" ? null : form.scope_id } }),
    onSuccess: () => { toast.success("Report requested — it will appear in this list when ready"); setOpen(false); void qc.invalidateQueries({ queryKey: ["reports"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <Card>
        <CardHeader
          title="Statutory compliance reports"
          subtitle="Monthly reports are generated automatically on the 1st (national + each subsidiary)"
          action={can("report:generate") && <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Generate report</Button>}
        />
        {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
          <EmptyState icon={<FileText className="h-6 w-6" />} title="No reports yet" />
        ) : (
          <Table>
            <thead><tr><Th>Report</Th><Th>Period</Th><Th>Status</Th><Th>Generated</Th><Th className="text-right">Download</Th></tr></thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id}>
                  <Td>
                    <span className="block font-medium">{r.title}</span>
                    <span className="text-xs text-muted">{humanize(r.scope)}{r.scheduled ? " · scheduled" : ""}</span>
                    {r.summary && <details className="mt-1 text-xs"><summary className="cursor-pointer text-copper-400">AI executive summary</summary><p className="mt-1 whitespace-pre-line text-muted">{r.summary}</p></details>}
                    {r.error && <span className="block text-xs text-bad">{r.error}</span>}
                  </Td>
                  <Td className="whitespace-nowrap">{fmtDate(r.period_start)} – {fmtDate(r.period_end)}</Td>
                  <Td><Badge tone={processingTone[r.status]}>{humanize(r.status)}</Badge></Td>
                  <Td>{r.generated_at ? fromNow(r.generated_at) : "—"}</Td>
                  <Td className="text-right whitespace-nowrap">
                    {r.has_pdf && <a href={`/api/files/report/${r.id}?format=pdf`} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm text-muted hover:bg-copper-500/10 hover:text-copper-600"><FileText className="h-4 w-4" /> PDF</a>}
                    {r.has_xlsx && <a href={`/api/files/report/${r.id}?format=xlsx`} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm text-muted hover:bg-copper-500/10 hover:text-copper-600"><FileSpreadsheet className="h-4 w-4" /> Excel</a>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="Generate compliance report">
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate(); }} className="space-y-4">
          <Field label="Scope" required>
            <Select value={form.scope} onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value, scope_id: "" }))}>
              <option value="mine">Mine</option>
              {me.role !== "mine_official" && <option value="subsidiary">Subsidiary</option>}
              {isGlobal && <option value="national">National</option>}
            </Select>
          </Field>
          {form.scope === "mine" && <Field label="Mine" required><MineSelect value={form.scope_id} onChange={(v) => setForm((f) => ({ ...f, scope_id: v }))} required /></Field>}
          {form.scope === "subsidiary" && (
            <Field label="Subsidiary" required>
              <Select value={form.scope_id} onChange={(e) => setForm((f) => ({ ...f, scope_id: e.target.value }))} required>
                <option value="">Select…</option>
                {subs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="From" required><Input type="date" value={form.period_start} onChange={(e) => setForm((f) => ({ ...f, period_start: e.target.value }))} required /></Field>
            <Field label="To" required><Input type="date" value={form.period_end} onChange={(e) => setForm((f) => ({ ...f, period_end: e.target.value }))} required /></Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={create.isPending}><Download className="h-4 w-4" /> Generate</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

function RiskTab() {
  const { can } = useSession();
  const [entity, setEntity] = useState<"mine" | "contractor">("mine");
  const [open, setOpen] = useState<string | null>(null);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["risk", entity],
    queryFn: () => api<RiskEntry[]>("/analytics/risk", { query: { entity_type: entity, limit: 100 } }),
  });
  const recompute = useMutation({
    mutationFn: () => api<{ workflow_id: string }>("/analytics/recompute", { method: "POST" }),
    onSuccess: () => toast.success("Risk model retraining & scoring started"),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader
        title="Compliance risk ranking"
        subtitle="Which mines are most likely to have a serious violation in the next 30 days, and why"
        action={
          <div className="flex gap-2">
            <Select value={entity} onChange={(e) => setEntity(e.target.value as "mine" | "contractor")} className="h-8 w-36 text-xs" aria-label="Entity">
              <option value="mine">Mines</option>
              <option value="contractor">Contractors</option>
            </Select>
            {can("analytics:run") && <Button size="sm" variant="outline" onClick={() => recompute.mutate()} loading={recompute.isPending}><RefreshCw className="h-4 w-4" /> Recompute</Button>}
          </div>
        }
      />
      {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.length ? (
        <EmptyState icon={<ChartColumn className="h-6 w-6" />} title="No risk scores yet" body="Scores are computed nightly and after each inspection." />
      ) : (
        <ul className="divide-y divide-line">
          {data.map((r, i) => (
            <li key={r.entity_id} className="px-5 py-3">
              <button className="flex w-full items-center gap-4 text-left" onClick={() => setOpen(open === r.entity_id ? null : r.entity_id)} aria-expanded={open === r.entity_id}>
                <span className="w-6 text-sm font-semibold text-muted tabular-nums">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{r.name}</span>
                  <span className="text-xs text-muted">{r.code} · {r.factors.drivers[0]?.label ?? "No adverse drivers"}</span>
                </span>
                <span className="hidden w-48 sm:block">
                  <span className="block h-2 overflow-hidden rounded-full bg-canvas">
                    <span className={cn("block h-full rounded-full", r.score >= 60 ? "bg-bad" : r.score >= 35 ? "bg-warn" : "bg-ok")} style={{ width: `${r.score}%` }} />
                  </span>
                </span>
                <span className="w-10 text-right font-bold tabular-nums">{r.score.toFixed(0)}</span>
                <Badge tone={bandTone[r.band]}>{humanize(r.band)}</Badge>
              </button>
              {open === r.entity_id && (
                <div className="mt-3 ml-10 grid grid-cols-1 gap-3 rounded-xl bg-canvas p-4 text-sm sm:grid-cols-2">
                  <div>
                    <p className="mb-2 font-semibold">Top risk drivers</p>
                    <ul className="space-y-1">
                      {r.factors.drivers.map((d) => (
                        <li key={d.feature} className="flex justify-between gap-2"><span>{d.label}</span><span className="tabular-nums text-muted">{d.value}</span></li>
                      ))}
                      {!r.factors.drivers.length && <li className="text-muted">None</li>}
                    </ul>
                  </div>
                  <div>
                    <p className="mb-2 font-semibold">All features</p>
                    <ul className="space-y-0.5 text-xs">
                      {Object.entries(r.factors.features).map(([k, v]) => (
                        <li key={k} className="flex justify-between gap-2"><span className="text-muted">{humanize(k)}</span><span className="tabular-nums">{v}</span></li>
                      ))}
                    </ul>
                    <p className="mt-2 text-xs text-muted">Computed {fmtDateTime(r.computed_at)}</p>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AnomaliesTab() {
  const qc = useQueryClient();
  const { can } = useSession();
  const [status, setStatus] = useState("open");
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["anomalies", status],
    queryFn: () => api<Page<Anomaly>>("/analytics/anomalies", { query: { status, size: 100 } }),
  });
  const update = useMutation({
    mutationFn: ({ id, s }: { id: string; s: string }) => api(`/analytics/anomalies/${id}`, { body: { status: s } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["anomalies"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader
        title="Unusual patterns"
        subtitle="Things the system noticed that need a look — repeated violations, sudden changes in output or attendance"
        action={
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 w-36 text-xs" aria-label="Status">
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </Select>
        }
      />
      {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
        <EmptyState title="No anomalies" body="The analytics engine has not flagged anything in this state." />
      ) : (
        <ul className="divide-y divide-line">
          {data.items.map((a) => (
            <li key={a.id} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-start">
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={a.kind === "recurring_violation" ? "bad" : a.kind === "attendance_drop" ? "warn" : "violet"}>{humanize(a.kind)}</Badge>
                  <span className="text-xs text-muted">score {a.score.toFixed(1)} · {fromNow(a.detected_at)}</span>
                </div>
                <p className="mt-1 font-medium">{a.title}</p>
                <p className="text-sm text-muted">{a.description}</p>
              </div>
              {can("violation:confirm") && a.status !== "resolved" && (
                <div className="flex gap-2">
                  {a.status === "open" && <Button size="sm" variant="outline" onClick={() => update.mutate({ id: a.id, s: "acknowledged" })}>Acknowledge</Button>}
                  <Button size="sm" variant="secondary" onClick={() => update.mutate({ id: a.id, s: "resolved" })}>Resolve</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TrendsTab() {
  const { data: trends } = useQuery({ queryKey: ["trends", 12], queryFn: () => api<{ label: string; month: string; total: number; critical: number; resolved: number }[]>("/analytics/trends", { query: { months: 12 } }) });
  const { data: cats } = useQuery({ queryKey: ["categories"], queryFn: () => api<{ category: string; low: number; medium: number; high: number; critical: number; total: number }[]>("/analytics/categories") });
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <Card>
        <CardHeader title="Violations — 12-month trend" />
        <div className="h-72 px-2 pb-4">
          <ResponsiveContainer>
            <LineChart data={trends ?? []} margin={{ top: 5, right: 16, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#24282d" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="total" name="Raised" stroke="#11513c" strokeWidth={2.5} />
              <Line dataKey="critical" name="Critical" stroke="#dc3a3a" strokeWidth={2.5} />
              <Line dataKey="resolved" name="Resolved" stroke="#3b6fd8" strokeWidth={2} strokeDasharray="4 3" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card>
        <CardHeader title="Violations by category & severity (12 months)" />
        <div className="h-72 px-2 pb-4">
          <ResponsiveContainer>
            <BarChart data={(cats ?? []).map((c) => ({ ...c, category: humanize(c.category) }))} margin={{ top: 5, right: 16, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#24282d" vertical={false} />
              <XAxis dataKey="category" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="low" stackId="a" fill="#3b6fd8" name="Low" />
              <Bar dataKey="medium" stackId="a" fill="#e0a100" name="Medium" />
              <Bar dataKey="high" stackId="a" fill="#f07a3a" name="High" />
              <Bar dataKey="critical" stackId="a" fill="#dc3a3a" name="Critical" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}

function ReportsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) ?? "reports");
  return (
    <div>
      <PageHeader title="Reports & Analytics" subtitle="Monthly statutory reports, mine risk ranking and unusual patterns" />
      <div className="mb-5">
        <Tabs<Tab>
          value={tab}
          onChange={(t) => { setTab(t); router.replace(`/reports?tab=${t}`); }}
          tabs={[{ value: "reports", label: "Reports" }, { value: "risk", label: "Risk scoring" }, { value: "anomalies", label: "Anomalies" }, { value: "trends", label: "Trends" }]}
        />
      </div>
      {tab === "reports" && <ReportsTab />}
      {tab === "risk" && <RiskTab />}
      {tab === "anomalies" && <AnomaliesTab />}
      {tab === "trends" && <TrendsTab />}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ReportsInner />
    </Suspense>
  );
}
