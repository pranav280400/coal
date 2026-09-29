"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, MessageSquareWarning, Plus, Smile, TriangleAlert, Inbox } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { MineSelect } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, Card, cn, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Tabs, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, grievanceTone, humanize, severityTone } from "@/lib/format";
import { CountUpValue, Stagger, StaggerItem } from "@/components/motion";
import { useI18n } from "@/lib/i18n";
import type { Grievance, GrievanceCategory, GrievanceSummary, Page } from "@/lib/types";

const GRIEVANCE_CATEGORIES: GrievanceCategory[] = [
  "wages", "safety", "working_conditions", "harassment", "welfare", "contractor_dispute", "environment", "other",
];
const STATUSES = ["open", "assigned", "in_progress", "resolved", "closed", "rejected"];
const PRIORITIES = ["low", "medium", "high", "critical"] as const;

type View = "all" | "raised" | "assigned";

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

function hours(h: number | null): string {
  if (h === null) return "—";
  return h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(0)} h`;
}

function RaiseModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const router = useRouter();
  const { t } = useI18n();
  const [form, setForm] = useState({
    mine_id: "",
    category: "safety" as GrievanceCategory,
    priority: "medium" as (typeof PRIORITIES)[number],
    subject: "",
    description: "",
    is_anonymous: false,
  });
  const create = useMutation({
    mutationFn: () => api<Grievance>("/grievances", { body: form }),
    onSuccess: (g) => {
      toast.success(t("Grievance raised"), { description: `GRV-${g.number}` });
      void qc.invalidateQueries({ queryKey: ["grievances"] });
      onClose();
      router.push(`/grievances/${g.id}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Modal open={open} onClose={onClose} title="Raise a grievance">
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate(); }} className="space-y-4">
        <Field label="Mine" required>
          <MineSelect value={form.mine_id} onChange={(v) => setForm((f) => ({ ...f, mine_id: v }))} required />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Category" required>
            <Select value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value as GrievanceCategory }))}>
              {GRIEVANCE_CATEGORIES.map((c) => <option key={c} value={c}>{t(humanize(c))}</option>)}
            </Select>
          </Field>
          <Field label="Priority" required>
            <Select value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value as (typeof PRIORITIES)[number] }))}>
              {PRIORITIES.map((p) => <option key={p} value={p}>{t(humanize(p))}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Subject" required>
          <Input value={form.subject} onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))} minLength={5} maxLength={300} required />
        </Field>
        <Field label="Description" required hint="What happened, where, since when, and who is affected.">
          <Textarea value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} minLength={10} rows={5} required />
        </Field>
        <label className="flex items-start gap-3 rounded-xl border border-line bg-canvas p-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 accent-copper-700"
            checked={form.is_anonymous}
            onChange={(e) => setForm((f) => ({ ...f, is_anonymous: e.target.checked }))}
          />
          <span>
            <span className="block font-medium">{t("Raise anonymously")}</span>
            <span className="block text-xs text-muted">{t("Your name is hidden from everyone except administrators.")}</span>
          </span>
        </label>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={create.isPending} disabled={!form.mine_id}>Raise grievance</Button>
        </div>
      </form>
    </Modal>
  );
}

function GrievancesInner() {
  const { can } = useSession();
  const params = useSearchParams();
  const { t } = useI18n();
  const [view, setView] = useState<View>("all");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [page, setPage] = useState(1);
  const [raising, setRaising] = useState(() => params.get("new") === "1" && can("grievance:raise"));
  const summary = useQuery({ queryKey: ["grievances", "summary"], queryFn: () => api<GrievanceSummary>("/grievances/summary") });
  const { data, error, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["grievances", view, status, category, overdue, page],
    queryFn: () => api<Page<Grievance>>("/grievances", { query: { view, status, category, overdue: overdue || undefined, page, size: 20 } }),
  });
  const s = summary.data;
  const tabs: { value: View; label: string }[] = [{ value: "all", label: "All in my scope" }];
  if (can("grievance:raise")) tabs.push({ value: "raised", label: "Raised by me" });
  if (can("grievance:manage")) tabs.push({ value: "assigned", label: "Assigned to me" });
  const reset = () => setPage(1);

  return (
    <div>
      <PageHeader
        title="Grievance Redressal"
        subtitle="Raise, track and resolve worker and contractor grievances within a deadline"
        actions={can("grievance:raise") && <Button onClick={() => setRaising(true)}><Plus className="h-4 w-4" /> Raise grievance</Button>}
      />
      <Stagger className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={<Inbox className="h-5 w-5" />} label="Open grievances" value={s?.open ?? "—"} />
        <Stat icon={<TriangleAlert className="h-5 w-5" />} label="Overdue" value={s?.overdue ?? "—"} tone={s?.overdue ? "bg-bad-soft text-bad" : undefined} />
        <Stat icon={<Clock className="h-5 w-5" />} label="Avg. resolution time" value={hours(s?.avg_resolution_hours ?? null)} />
        <Stat icon={<Smile className="h-5 w-5" />} label="Satisfaction" value={s?.avg_satisfaction ? `${s.avg_satisfaction.toFixed(1)} / 5` : "—"} />
      </Stagger>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {tabs.length > 1 && <Tabs<View> value={view} onChange={(v) => { setView(v); reset(); }} tabs={tabs} />}
        <Select value={status} onChange={(e) => { setStatus(e.target.value); reset(); }} className="w-44" aria-label={t("Status")}>
          <option value="">{t("All")} · {t("Status")}</option>
          {STATUSES.map((x) => <option key={x} value={x}>{t(humanize(x))}</option>)}
        </Select>
        <Select value={category} onChange={(e) => { setCategory(e.target.value); reset(); }} className="w-52" aria-label={t("Category")}>
          <option value="">{t("All")} · {t("Category")}</option>
          {GRIEVANCE_CATEGORIES.map((c) => <option key={c} value={c}>{t(humanize(c))}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="accent-copper-700" checked={overdue} onChange={(e) => { setOverdue(e.target.checked); reset(); }} />
          {t("Only overdue")}
        </label>
      </div>
      <Card>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <EmptyState icon={<MessageSquareWarning className="h-6 w-6" />} title="No grievances" body="No grievances match these filters." />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Grievance</Th>
                  <Th>Category</Th>
                  <Th>Priority</Th>
                  <Th>Status</Th>
                  <Th>Resolve by</Th>
                  <Th>Raised by</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((g) => {
                  const active = ["open", "assigned", "in_progress"].includes(g.status);
                  const late = active && new Date(g.due_at).getTime() < dataUpdatedAt;
                  return (
                    <tr key={g.id} className="hover:bg-fg/5/60">
                      <Td>
                        <Link href={`/grievances/${g.id}`} className="font-medium hover:text-copper-400">
                          <span className="text-muted">GRV-{g.number}</span> · {g.subject}
                        </Link>
                        <span className="block text-xs text-muted">{g.mine.name}</span>
                      </Td>
                      <Td className="whitespace-nowrap">{t(humanize(g.category))}</Td>
                      <Td><Badge tone={severityTone[g.priority]}>{humanize(g.priority)}</Badge></Td>
                      <Td>
                        <span className="flex flex-wrap items-center gap-1.5">
                          <Badge tone={grievanceTone[g.status]}>{humanize(g.status)}</Badge>
                          {g.escalation_level > 0 && active && <Badge tone="bad">L{g.escalation_level}</Badge>}
                        </span>
                      </Td>
                      <Td className={cn("whitespace-nowrap", late && "font-semibold text-bad")}>{fmtDateTime(g.due_at)}</Td>
                      <Td>{g.raiser ? g.raiser.full_name : <span className="text-muted italic">{t("Anonymous")}</span>}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <Pagination page={page} size={20} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      <RaiseModal open={raising} onClose={() => setRaising(false)} />
    </div>
  );
}

export default function GrievancesPage() {
  return (
    <Suspense fallback={<Loading />}>
      <GrievancesInner />
    </Suspense>
  );
}
