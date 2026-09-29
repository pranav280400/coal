"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Droplets, Leaf, Plus, ShieldCheck, TriangleAlert, Volume2, Wind } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { GeoCapture, MineSelect, type GeoValue } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, Card, CardHeader, cn, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtNumber } from "@/lib/format";
import { CountUpValue, Stagger, StaggerItem } from "@/components/motion";
import { useI18n } from "@/lib/i18n";
import type { EnvLimit, EnvParameter, EnvReading, EnvSummary, Page } from "@/lib/types";

const GROUP_ICON = { air: Wind, noise: Volume2, water: Droplets } as const;
const GROUP_LABEL = { air: "Air", noise: "Noise", water: "Water" } as const;

function limitText(l: { limit_min: number | null; limit_max: number | null; unit: string }): string {
  if (l.limit_min !== null && l.limit_max !== null) return `${l.limit_min}–${l.limit_max} ${l.unit}`;
  return `≤ ${l.limit_max} ${l.unit}`;
}

function isOver(l: EnvLimit | undefined, v: number): boolean {
  if (!l || Number.isNaN(v)) return false;
  return (l.limit_max !== null && v > l.limit_max) || (l.limit_min !== null && v < l.limit_min);
}

function Stat({ icon, label, value, tone }: { icon: ReactNode; label: string; value: ReactNode; tone?: string }) {
  const { t } = useI18n();
  return (
    <StaggerItem>
    <Card className="flex h-full items-center gap-4 p-4">
      <span className={cn("grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-copper-50 text-copper-400", tone)}>{icon}</span>
      <span className="min-w-0">
        <span className="block text-2xl font-bold tracking-tight tabular-nums"><CountUpValue value={value} /></span>
        <span className="block text-xs leading-snug text-muted">{t(label)}</span>
      </span>
    </Card>
    </StaggerItem>
  );
}

function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function RecordModal({ open, onClose, limits, defaultMine }: { open: boolean; onClose: () => void; limits: EnvLimit[]; defaultMine: string }) {
  const qc = useQueryClient();
  const { t } = useI18n();
  const [geo, setGeo] = useState<GeoValue | null>(null);
  const [form, setForm] = useState({
    mine_id: defaultMine,
    parameter: "pm10" as EnvParameter,
    value: "",
    station: "Core zone AAQ station",
    sampled_at: nowLocal(),
    source: "manual",
    notes: "",
  });
  const limit = limits.find((l) => l.parameter === form.parameter);
  const over = isOver(limit, Number(form.value));
  const save = useMutation({
    mutationFn: () =>
      api<EnvReading>("/environment/readings", {
        body: {
          mine_id: form.mine_id,
          parameter: form.parameter,
          value: Number(form.value),
          station: form.station,
          sampled_at: new Date(form.sampled_at).toISOString(),
          source: form.source,
          geo: geo ? { latitude: geo.latitude, longitude: geo.longitude } : null,
          notes: form.notes || null,
        },
      }),
    onSuccess: (r) => {
      if (r.exceeded) toast.warning(t("Above the statutory limit — an environment violation was opened"));
      else toast.success(t("Reading recorded"));
      void qc.invalidateQueries({ queryKey: ["environment"] });
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Modal open={open} onClose={onClose} title="Record reading">
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
        <Field label="Mine" required>
          <MineSelect value={form.mine_id} onChange={(v) => setForm((f) => ({ ...f, mine_id: v }))} required />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Parameter" required>
            <Select value={form.parameter} onChange={(e) => setForm((f) => ({ ...f, parameter: e.target.value as EnvParameter }))}>
              {(["air", "noise", "water"] as const).map((g) => (
                <optgroup key={g} label={t(GROUP_LABEL[g])}>
                  {limits.filter((l) => l.group === g).map((l) => <option key={l.parameter} value={l.parameter}>{l.label} ({l.unit})</option>)}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="Reading" required hint={limit ? `${t("Statutory limit")}: ${limitText(limit)}` : undefined}>
            <Input
              type="number"
              step="any"
              value={form.value}
              onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
              className={over ? "border-bad focus:border-bad focus:ring-bad-soft" : undefined}
              required
            />
          </Field>
          <Field label="Monitoring station" required>
            <Input value={form.station} onChange={(e) => setForm((f) => ({ ...f, station: e.target.value }))} required minLength={2} />
          </Field>
          <Field label="Sampled at" required>
            <Input type="datetime-local" value={form.sampled_at} max={nowLocal()} onChange={(e) => setForm((f) => ({ ...f, sampled_at: e.target.value }))} required />
          </Field>
          <Field label="Source">
            <Select value={form.source} onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}>
              <option value="manual">{t("Manual")}</option>
              <option value="lab">{t("Lab")}</option>
              <option value="sensor">{t("Sensor")}</option>
            </Select>
          </Field>
        </div>
        {limit && <p className="text-xs text-muted">{limit.standard}</p>}
        {over && (
          <p className="flex items-center gap-2 rounded-xl bg-bad-soft px-3 py-2 text-sm text-bad">
            <TriangleAlert className="h-4 w-4 shrink-0" /> {t("Above the statutory limit — an environment violation was opened")}
          </p>
        )}
        <Field label="Location (geo-tag)"><GeoCapture value={geo} onChange={setGeo} /></Field>
        <Field label="Notes"><Textarea value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} rows={2} /></Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={save.isPending} disabled={!form.mine_id || form.value === ""}>Record</Button>
        </div>
      </form>
    </Modal>
  );
}

function EnvironmentInner() {
  const { can, me } = useSession();
  const params = useSearchParams();
  const { t } = useI18n();
  const [mine, setMine] = useState("");
  const [selected, setSelected] = useState<EnvParameter>("pm10");
  const [paramFilter, setParamFilter] = useState("");
  const [onlyExceeded, setOnlyExceeded] = useState(false);
  const [page, setPage] = useState(1);
  const [recording, setRecording] = useState(() => params.get("new") === "1" && can("operations:write"));
  const { data: limits = [] } = useQuery({ queryKey: ["environment", "limits"], queryFn: () => api<EnvLimit[]>("/environment/limits"), staleTime: Infinity });
  const summary = useQuery({ queryKey: ["environment", "summary", mine], queryFn: () => api<EnvSummary>("/environment/summary", { query: { mine_id: mine } }) });
  const trend = useQuery({
    queryKey: ["environment", "trend", selected, mine],
    queryFn: () => api<{ day: string; average: number; maximum: number }[]>("/environment/trend", { query: { parameter: selected, mine_id: mine, days: 90 } }),
  });
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["environment", "readings", mine, paramFilter, onlyExceeded, page],
    queryFn: () =>
      api<Page<EnvReading>>("/environment/readings", {
        query: { mine_id: mine, parameter: paramFilter, exceeded: onlyExceeded ? true : undefined, page, size: 20 },
      }),
  });
  const s = summary.data;
  const sel = limits.find((l) => l.parameter === selected);
  const labelOf = useMemo(() => Object.fromEntries(limits.map((l) => [l.parameter, l.label])), [limits]);
  const chart = (trend.data ?? []).map((p) => ({ day: fmtDate(p.day, "dd MMM"), [t("Daily average")]: p.average, [t("Daily peak")]: p.maximum }));

  return (
    <div>
      <PageHeader
        title="Environmental Monitoring"
        subtitle="Air, noise and effluent readings checked against statutory limits — breaches open a violation automatically"
        actions={
          <>
            <div className="w-64"><MineSelect value={mine} onChange={(v) => { setMine(v); setPage(1); }} allowAll /></div>
            {can("operations:write") && <Button onClick={() => setRecording(true)}><Plus className="h-4 w-4" /> Record reading</Button>}
          </>
        }
      />
      <Stagger className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat icon={<Activity className="h-5 w-5" />} label="Readings (30 days)" value={s ? fmtNumber(s.readings_30d) : "—"} />
        <Stat icon={<TriangleAlert className="h-5 w-5" />} label="Exceedances (30 days)" value={s?.exceedances_30d ?? "—"} tone={s?.exceedances_30d ? "bg-bad-soft text-bad" : undefined} />
        <Stat icon={<ShieldCheck className="h-5 w-5" />} label="Within limits (30 days)" value={s?.compliance_pct != null ? `${s.compliance_pct}%` : "—"} tone="bg-ok-soft text-ok" />
      </Stagger>

      <Stagger className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" step={0.04}>
        {(s?.parameters ?? []).map((p) => {
          const Icon = GROUP_ICON[p.group];
          const over = p.latest !== null && isOver(limits.find((l) => l.parameter === p.parameter), p.latest);
          return (
            <StaggerItem key={p.parameter}>
            <button
              type="button"
              onClick={() => setSelected(p.parameter)}
              className={cn(
                "h-full w-full rounded-2xl border bg-surface p-4 text-left shadow-card transition hover:border-copper-500/60",
                selected === p.parameter ? "border-copper-500 ring-2 ring-copper-500/25" : "border-line",
              )}
            >
              <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted">
                <span className="flex items-center gap-1.5"><Icon className="h-3.5 w-3.5" /> {p.label}</span>
                {p.exceedances_30d > 0 && <Badge tone="bad">{p.exceedances_30d}</Badge>}
              </span>
              <span className={cn("mt-2 block text-xl font-bold tabular-nums", over && "text-bad")}>
                {p.latest !== null ? fmtNumber(p.latest, 1) : "—"} <span className="text-xs font-medium text-muted">{p.unit}</span>
              </span>
              <span className="mt-1 block text-[11px] text-muted">
                {t("Limit")} {limitText(p)} · {t("30-day average")} {p.average_30d !== null ? fmtNumber(p.average_30d, 1) : "—"}
              </span>
            </button>
            </StaggerItem>
          );
        })}
      </Stagger>

      <div className="mb-5 grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title={`${sel?.label ?? ""} — ${t("Daily average and peak — 90 days")}`} subtitle={sel ? `${t("Statutory limit")}: ${limitText(sel)} · ${sel.standard}` : undefined} />
          <div className="h-72 px-2 pb-4">
            {trend.isLoading ? <Loading /> : !chart.length ? <EmptyState title="No readings yet" /> : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart} margin={{ left: 0, right: 12, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#24282d" vertical={false} />
                  <XAxis dataKey="day" tick={{ fontSize: 11 }} minTickGap={24} />
                  <YAxis tick={{ fontSize: 11 }} width={44} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {sel?.limit_max != null && <ReferenceLine y={sel.limit_max} stroke="#cf4034" strokeDasharray="6 4" label={{ value: t("Limit"), fontSize: 11, fill: "#cf4034", position: "insideTopRight" }} />}
                  {sel?.limit_min != null && <ReferenceLine y={sel.limit_min} stroke="#cf4034" strokeDasharray="6 4" />}
                  <Line type="monotone" dataKey={t("Daily average")} stroke="#b86b35" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey={t("Daily peak")} stroke="#596269" strokeWidth={1.5} dot={false} strokeDasharray="3 3" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="Most exceedances (30 days)" />
          <div className="px-5 pb-5">
            {!s?.worst_mines.length ? (
              <p className="text-sm text-muted">{t("No exceedances in the last 30 days.")}</p>
            ) : (
              <ul className="divide-y divide-line">
                {s.worst_mines.map((m) => (
                  <li key={m.mine_id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <button type="button" onClick={() => setMine(m.mine_id)} className="min-w-0 truncate text-left font-medium hover:text-copper-400">
                      {m.name} <span className="text-xs text-muted">{m.code}</span>
                    </button>
                    <Badge tone="bad">{m.exceedances}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Recent readings"
          action={
            <div className="flex flex-wrap items-center gap-3">
              <Select value={paramFilter} onChange={(e) => { setParamFilter(e.target.value); setPage(1); }} className="w-48" aria-label={t("Parameter")}>
                <option value="">{t("All")} · {t("Parameter")}</option>
                {limits.map((l) => <option key={l.parameter} value={l.parameter}>{l.label}</option>)}
              </Select>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="accent-copper-700" checked={onlyExceeded} onChange={(e) => { setOnlyExceeded(e.target.checked); setPage(1); }} />
                {t("Only exceedances")}
              </label>
            </div>
          }
        />
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <EmptyState icon={<Leaf className="h-6 w-6" />} title="No readings yet" />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Sampled</Th>
                  <Th>Mine</Th>
                  <Th>Parameter</Th>
                  <Th className="text-right">Reading</Th>
                  <Th>Limit</Th>
                  <Th>Station</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id} className="hover:bg-fg/5/60">
                    <Td className="whitespace-nowrap">{fmtDateTime(r.sampled_at)}</Td>
                    <Td>{r.mine.name}</Td>
                    <Td className="whitespace-nowrap">{labelOf[r.parameter] ?? r.parameter}</Td>
                    <Td className={cn("text-right font-semibold tabular-nums", r.exceeded && "text-bad")}>{fmtNumber(r.value, 2)} <span className="text-xs font-normal text-muted">{r.unit}</span></Td>
                    <Td className="whitespace-nowrap text-muted">{limitText(r)}</Td>
                    <Td>{r.station}<span className="block text-xs text-muted">{t(r.source === "lab" ? "Lab" : r.source === "sensor" ? "Sensor" : "Manual")}</span></Td>
                    <Td>
                      {r.exceeded ? (
                        r.violation_id ? (
                          <Link href={`/violations/${r.violation_id}`}><Badge tone="bad">{t("Violation opened")} →</Badge></Link>
                        ) : (
                          <Badge tone="bad">Above limit</Badge>
                        )
                      ) : (
                        <Badge tone="ok">Within limit</Badge>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} size={20} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {recording && <RecordModal open onClose={() => setRecording(false)} limits={limits} defaultMine={mine || me.mine_id || ""} />}
    </div>
  );
}

export default function EnvironmentPage() {
  return (
    <Suspense fallback={<Loading />}>
      <EnvironmentInner />
    </Suspense>
  );
}
