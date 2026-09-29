"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Factory, Gauge, Plus, TrendingDown, TrendingUp, Truck } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { MineSelect } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, Card, CardHeader, cn, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Pagination, Table, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtNumber, fmtTonnes } from "@/lib/format";
import { CountUpValue, GrowBar, Stagger, StaggerItem } from "@/components/motion";
import { useI18n } from "@/lib/i18n";
import type { Page, ProductionRecord, ProductionSummary } from "@/lib/types";

function Stat({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; tone?: string }) {
  const { t } = useI18n();
  return (
    <StaggerItem>
    <Card className="flex h-full items-center gap-4 p-4">
      <span className={cn("grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-copper-50 text-copper-400", tone)}>{icon}</span>
      <span className="min-w-0">
        <span className="block text-2xl font-bold tracking-tight tabular-nums"><CountUpValue value={value} /></span>
        <span className="block text-xs leading-snug text-muted">{t(label)}</span>
        {sub && <span className="block text-xs text-muted">{sub}</span>}
      </span>
    </Card>
    </StaggerItem>
  );
}

function lastMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function RecordModal({ open, onClose, defaultMine }: { open: boolean; onClose: () => void; defaultMine: string }) {
  const qc = useQueryClient();
  const { t } = useI18n();
  const [form, setForm] = useState({
    mine_id: defaultMine,
    month: lastMonth(),
    target_t: "",
    produced_t: "",
    dispatched_t: "",
    overburden_bcm: "",
    closing_stock_t: "",
    notes: "",
  });
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const save = useMutation({
    mutationFn: () =>
      api<ProductionRecord>("/production", {
        method: "PUT",
        body: {
          mine_id: form.mine_id,
          period: `${form.month}-01`,
          target_t: num(form.target_t),
          produced_t: num(form.produced_t),
          dispatched_t: num(form.dispatched_t),
          overburden_bcm: num(form.overburden_bcm),
          closing_stock_t: num(form.closing_stock_t),
          notes: form.notes || null,
        },
      }),
    onSuccess: () => {
      toast.success(t("Return saved"));
      void qc.invalidateQueries({ queryKey: ["production"] });
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <Modal open={open} onClose={onClose} title="Record monthly return">
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Mine" required>
            <MineSelect value={form.mine_id} onChange={(v) => setForm((f) => ({ ...f, mine_id: v }))} required />
          </Field>
          <Field label="Month" required hint="Re-entering a month corrects that month's return.">
            <Input type="month" value={form.month} onChange={set("month")} max={lastMonth()} required />
          </Field>
          <Field label="Target (t)"><Input type="number" min={0} step="any" value={form.target_t} onChange={set("target_t")} /></Field>
          <Field label="Coal produced (t)" required><Input type="number" min={0} step="any" value={form.produced_t} onChange={set("produced_t")} required /></Field>
          <Field label="Coal despatched (t)" required><Input type="number" min={0} step="any" value={form.dispatched_t} onChange={set("dispatched_t")} required /></Field>
          <Field label="Overburden removed (BCM)"><Input type="number" min={0} step="any" value={form.overburden_bcm} onChange={set("overburden_bcm")} /></Field>
          <Field label="Closing stock (t)"><Input type="number" min={0} step="any" value={form.closing_stock_t} onChange={set("closing_stock_t")} /></Field>
        </div>
        <Field label="Notes"><Textarea value={form.notes} onChange={set("notes")} rows={2} /></Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={save.isPending} disabled={!form.mine_id}>Save</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function ProductionPage() {
  const { can, me } = useSession();
  const { t } = useI18n();
  const [mine, setMine] = useState("");
  const [page, setPage] = useState(1);
  const [recording, setRecording] = useState(false);
  const summary = useQuery({
    queryKey: ["production", "summary", mine],
    queryFn: () => api<ProductionSummary>("/production/summary", { query: { mine_id: mine } }),
  });
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["production", "list", mine, page],
    queryFn: () => api<Page<ProductionRecord>>("/production", { query: { mine_id: mine, page, size: 25 } }),
  });
  const s = summary.data;
  const chart = (s?.months ?? []).map((m) => ({
    month: fmtDate(m.period, "MMM yy"),
    [t("Target")]: Math.round(m.target_t / 1000),
    [t("Produced")]: Math.round(m.produced_t / 1000),
    [t("Despatched")]: Math.round(m.dispatched_t / 1000),
  }));
  const change = s?.last_month_change_pct ?? null;

  return (
    <div>
      <PageHeader
        title="Production & Despatch"
        subtitle="Monthly production returns against target, with despatch and overburden removal"
        actions={
          <>
            <div className="w-64"><MineSelect value={mine} onChange={(v) => { setMine(v); setPage(1); }} allowAll /></div>
            {can("operations:write") && <Button onClick={() => setRecording(true)}><Plus className="h-4 w-4" /> Record monthly return</Button>}
          </>
        }
      />
      <Stagger className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={<Factory className="h-5 w-5" />} label="Produced this financial year" value={fmtTonnes(s?.ytd_produced_t)} />
        <Stat icon={<Truck className="h-5 w-5" />} label="Despatched this financial year" value={fmtTonnes(s?.ytd_dispatched_t)} />
        <Stat
          icon={<Gauge className="h-5 w-5" />}
          label="Target achievement (FY)"
          value={s?.achievement_pct != null ? `${s.achievement_pct}%` : "—"}
          tone={s?.achievement_pct != null && s.achievement_pct < 90 ? "bg-warn-soft text-warn" : undefined}
        />
        <Stat
          icon={change !== null && change < 0 ? <TrendingDown className="h-5 w-5" /> : <TrendingUp className="h-5 w-5" />}
          label="Change vs previous month"
          value={change !== null ? `${change > 0 ? "+" : ""}${change}%` : "—"}
          tone={change !== null && change < -10 ? "bg-bad-soft text-bad" : undefined}
        />
      </Stagger>

      <div className="mb-5 grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Production vs target — 12 months" subtitle="'000 t" />
          <div className="h-72 px-2 pb-4">
            {summary.isLoading ? <Loading /> : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chart} margin={{ left: 0, right: 12, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#24282d" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} width={48} />
                  <Tooltip formatter={(v) => `${fmtNumber(Number(v))} kt`} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey={t("Produced")} fill="#b86b35" radius={[4, 4, 0, 0]} />
                  <Bar dataKey={t("Despatched")} fill="#596269" radius={[4, 4, 0, 0]} />
                  <Line dataKey={t("Target")} stroke="#121416" strokeWidth={2} strokeDasharray="5 4" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="Mines below 85% of target last month" />
          <div className="px-5 pb-5">
            {!s?.shortfall_mines.length ? (
              <p className="text-sm text-muted">{t("Every mine met at least 85% of its target.")}</p>
            ) : (
              <ul className="space-y-3">
                {s.shortfall_mines.map((m) => (
                  <li key={m.mine_id}>
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="min-w-0 truncate font-medium">{m.name}</span>
                      <Badge tone={m.achievement_pct < 70 ? "bad" : "warn"}>{m.achievement_pct}%</Badge>
                    </div>
                    <GrowBar pct={m.achievement_pct} className="mt-1.5 h-1.5" barClassName={m.achievement_pct < 70 ? "bg-bad" : "bg-warn"} />
                    <p className="mt-1 text-xs text-muted">{fmtTonnes(m.produced_t)} / {fmtTonnes(m.target_t)}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Monthly returns" />
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <EmptyState icon={<Factory className="h-6 w-6" />} title="No production returns yet" />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Month</Th>
                  <Th>Mine</Th>
                  <Th className="text-right">Target</Th>
                  <Th className="text-right">Produced</Th>
                  <Th className="text-right">Achievement</Th>
                  <Th className="text-right">Despatched</Th>
                  <Th className="text-right">Overburden</Th>
                  <Th className="text-right">Closing stock</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => {
                  const pct = r.target_t ? Math.round((100 * r.produced_t) / r.target_t) : null;
                  return (
                    <tr key={r.id} className="hover:bg-fg/5/60">
                      <Td className="whitespace-nowrap font-medium">{fmtDate(r.period, "MMM yyyy")}</Td>
                      <Td>{r.mine.name}<span className="block text-xs text-muted">{r.mine.code}</span></Td>
                      <Td className="text-right tabular-nums">{fmtTonnes(r.target_t)}</Td>
                      <Td className="text-right tabular-nums">{fmtTonnes(r.produced_t)}</Td>
                      <Td className="text-right">{pct === null ? "—" : <Badge tone={pct >= 95 ? "ok" : pct >= 85 ? "warn" : "bad"}>{pct}%</Badge>}</Td>
                      <Td className="text-right tabular-nums">{fmtTonnes(r.dispatched_t)}</Td>
                      <Td className="text-right tabular-nums">{r.overburden_bcm != null ? `${fmtNumber(r.overburden_bcm / 1000, 1)}k m³` : "—"}</Td>
                      <Td className="text-right tabular-nums">{fmtTonnes(r.closing_stock_t)}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <Pagination page={page} size={25} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {recording && <RecordModal open onClose={() => setRecording(false)} defaultMine={mine || me.mine_id || ""} />}
    </div>
  );
}
