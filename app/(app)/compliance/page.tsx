"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, ClipboardCheck, Pencil, Plus, Trash } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { MineSelect, Timeline } from "@/components/common";
import { useSession } from "@/components/session";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  KeyValue,
  Loading,
  Modal,
  PageHeader,
  Pagination,
  Select,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { complianceTone, fmtDate, fmtDateTime, humanize } from "@/lib/format";
import type { Category, ComplianceItem, ComplianceSummary, Page, Regulation } from "@/lib/types";

const CATEGORIES: Category[] = ["safety", "environment", "production", "labour"];
const STATUSES = ["due", "in_progress", "overdue", "violated", "compliant"];
const FREQUENCIES = ["one_time", "monthly", "quarterly", "half_yearly", "annual"];

function daysLeft(due: string): number {
  const d = new Date(`${due}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86_400_000);
}

function ItemForm({ item, onDone }: { item?: ComplianceItem; onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    mine_id: item?.mine_id ?? "",
    category: item?.category ?? ("safety" as Category),
    title: item?.title ?? "",
    description: item?.description ?? "",
    regulation_id: item?.regulation_id ?? "",
    regulation_ref: item?.regulation_ref ?? "",
    frequency: item?.frequency ?? "one_time",
    due_date: item?.due_date ?? "",
    status: item?.status ?? "due",
  });
  const { data: regs } = useQuery({
    queryKey: ["regulations", form.category],
    queryFn: () => api<Page<Regulation>>("/regulations", { query: { category: form.category, size: 200 } }),
  });
  const save = useMutation({
    mutationFn: () =>
      item
        ? api<ComplianceItem>(`/compliance/${item.id}`, {
            method: "PATCH",
            body: {
              title: form.title,
              description: form.description || null,
              regulation_ref: form.regulation_ref || null,
              frequency: form.frequency,
              due_date: form.due_date,
              status: form.status,
            },
          })
        : api<ComplianceItem>("/compliance", {
            body: {
              mine_id: form.mine_id,
              category: form.category,
              title: form.title,
              description: form.description || null,
              regulation_id: form.regulation_id || null,
              regulation_ref: form.regulation_ref || null,
              frequency: form.frequency,
              due_date: form.due_date,
            },
          }),
    onSuccess: () => {
      toast.success(item ? "Compliance item updated" : "Compliance item created — reminders scheduled");
      void qc.invalidateQueries({ queryKey: ["compliance"] });
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
      className="space-y-4"
    >
      {!item && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Mine" required>
            <MineSelect value={form.mine_id} onChange={(v) => setForm((f) => ({ ...f, mine_id: v }))} required />
          </Field>
          <Field label="Category" required>
            <Select value={form.category} onChange={set("category")}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      )}
      <Field label="Obligation" required>
        <Input value={form.title} onChange={set("title")} required minLength={3} placeholder="e.g. Monthly ambient air quality report" />
      </Field>
      {!item && (
        <Field label="Statutory provision" hint="Linking a regulation enables AI guidance and citations">
          <Select value={form.regulation_id} onChange={set("regulation_id")}>
            <option value="">— none —</option>
            {regs?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.act} — {r.section ?? r.code}: {r.title}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Field label="Reference (free text)">
        <Input value={form.regulation_ref} onChange={set("regulation_ref")} placeholder="e.g. CMR 2017 Reg. 145" />
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Frequency" required>
          <Select value={form.frequency} onChange={set("frequency")}>
            {FREQUENCIES.map((f) => (
              <option key={f} value={f}>
                {humanize(f)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Due date" required>
          <Input type="date" value={form.due_date} onChange={set("due_date")} required />
        </Field>
      </div>
      {item && (
        <Field label="Status">
          <Select value={form.status} onChange={set("status")}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Field label="Description">
        <Textarea value={form.description} onChange={set("description")} />
      </Field>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending}>
          {item ? "Save changes" : "Create item"}
        </Button>
      </div>
    </form>
  );
}

function CompleteForm({ item, onDone }: { item: ComplianceItem; onDone: () => void }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const complete = useMutation({
    mutationFn: async () => {
      let evidence: string | null = null;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("title", `Evidence — ${item.title}`);
        form.append("doc_type", "evidence");
        form.append("mine_id", item.mine_id);
        evidence = (await api<{ id: string }>("/documents", { method: "POST", form })).id;
      }
      return api<ComplianceItem>(`/compliance/${item.id}/complete`, { body: { notes, evidence_document_id: evidence } });
    },
    onSuccess: (res) => {
      toast.success(res.status === "due" ? `Marked complete — next due ${fmtDate(res.due_date)}` : "Marked compliant");
      void qc.invalidateQueries({ queryKey: ["compliance"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        complete.mutate();
      }}
      className="space-y-4"
    >
      <p className="text-sm text-muted">
        Recording completion of <strong className="text-ink">{item.title}</strong>
        {item.frequency !== "one_time" && " — the next statutory period will be scheduled automatically."}
      </p>
      <Field label="Completion notes" required>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} required minLength={3} placeholder="What was submitted, to whom, reference numbers…" />
      </Field>
      <Field label="Evidence document (PDF / image)" hint="The document is read automatically and added to the searchable record">
        <Input type="file" accept="application/pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="py-2" />
      </Field>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={complete.isPending}>
          <CircleCheck className="h-4 w-4" /> Mark complete
        </Button>
      </div>
    </form>
  );
}

function CompliancePageInner() {
  const { can } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [filters, setFilters] = useState({ mine_id: "", category: "", status: params.get("status") ?? "", q: "" });
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState<{ kind: "new" | "edit" | "complete" | "view"; item?: ComplianceItem } | null>(null);
  const focus = params.get("item");

  const { data: summary } = useQuery({
    queryKey: ["compliance", "summary", filters.mine_id],
    queryFn: () => api<ComplianceSummary>("/compliance/summary", { query: { mine_id: filters.mine_id } }),
  });
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["compliance", "list", filters, page],
    queryFn: () => api<Page<ComplianceItem>>("/compliance", { query: { ...filters, page, size: 20 } }),
  });
  useEffect(() => {
    if (!focus) return;
    api<ComplianceItem>(`/compliance/${focus}`)
      .then((item) => setModal({ kind: "view", item }))
      .catch(() => undefined);
  }, [focus]);
  const remove = useMutation({
    mutationFn: (id: string) => api(`/compliance/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Deleted");
      void qc.invalidateQueries({ queryKey: ["compliance"] });
      setModal(null);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const close = () => {
    setModal(null);
    if (focus) router.replace("/compliance");
  };
  const writable = can("compliance:write");

  return (
    <div>
      <PageHeader
        title="Statutory Compliance"
        subtitle="Legal obligations for each mine, with reminders before they fall due"
        actions={
          writable && (
            <Button onClick={() => setModal({ kind: "new" })}>
              <Plus className="h-4 w-4" /> New obligation
            </Button>
          )
        }
      />

      {summary && (
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Card className="p-4">
            <p className="text-xs text-muted">On track</p>
            <p className="text-2xl font-bold">{Math.round(summary.compliance_rate)}%</p>
            <p className="text-xs text-muted">{summary.total} obligations</p>
          </Card>
          {CATEGORIES.map((c) => {
            const row = summary.by_category[c] ?? {};
            const total = Object.values(row).reduce((a, b) => a + b, 0);
            const bad = (row.overdue ?? 0) + (row.violated ?? 0);
            return (
              <button
                key={c}
                onClick={() => setFilters((f) => ({ ...f, category: f.category === c ? "" : c }))}
                className={`rounded-2xl border bg-surface p-4 text-left shadow-card ${filters.category === c ? "border-copper-500" : "border-line"}`}
              >
                <p className="text-xs text-muted">{humanize(c)}</p>
                <p className="text-2xl font-bold">{total}</p>
                <p className={`text-xs font-semibold ${bad ? "text-bad" : "text-ok"}`}>{bad ? `${bad} overdue / violated` : "No overdue items"}</p>
              </button>
            );
          })}
        </div>
      )}

      <Card>
        <div className="filterbar grid grid-cols-1 gap-3 border-b border-line p-4 sm:grid-cols-4">
          <MineSelect allowAll value={filters.mine_id} onChange={(v) => { setFilters((f) => ({ ...f, mine_id: v })); setPage(1); }} />
          <Select value={filters.category} onChange={(e) => { setFilters((f) => ({ ...f, category: e.target.value })); setPage(1); }} aria-label="Category">
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
          </Select>
          <Select value={filters.status} onChange={(e) => { setFilters((f) => ({ ...f, status: e.target.value })); setPage(1); }} aria-label="Status">
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
          <Input placeholder="Search obligation or regulation…" value={filters.q} onChange={(e) => { setFilters((f) => ({ ...f, q: e.target.value })); setPage(1); }} />
        </div>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <EmptyState icon={<ClipboardCheck className="h-6 w-6" />} title="No obligations match" body="Adjust the filters or add a statutory obligation." />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Obligation</Th>
                  <Th>Mine</Th>
                  <Th>Category</Th>
                  <Th>Due</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => {
                  const dl = daysLeft(item.due_date);
                  return (
                    <tr key={item.id} className="hover:bg-fg/5/60">
                      <Td>
                        <button className="text-left" onClick={() => setModal({ kind: "view", item })}>
                          <span className="block font-medium hover:text-copper-400">{item.title}</span>
                          <span className="block text-xs text-muted">{item.regulation_ref ?? humanize(item.frequency)}</span>
                        </button>
                      </Td>
                      <Td>{item.mine.name}</Td>
                      <Td>{humanize(item.category)}</Td>
                      <Td>
                        <span className="block">{fmtDate(item.due_date)}</span>
                        {item.status !== "compliant" && (
                          <span className={`text-xs font-medium ${dl < 0 ? "text-bad" : dl <= 7 ? "text-warn" : "text-muted"}`}>
                            {dl < 0 ? `${-dl} days overdue` : dl === 0 ? "due today" : `in ${dl} days`}
                          </span>
                        )}
                      </Td>
                      <Td>
                        <Badge tone={complianceTone[item.status]}>{humanize(item.status)}</Badge>
                        {item.escalated && <Badge tone="bad" className="ml-1">Escalated</Badge>}
                      </Td>
                      <Td className="text-right whitespace-nowrap">
                        {writable && item.status !== "compliant" && (
                          <Button size="sm" variant="secondary" onClick={() => setModal({ kind: "complete", item })}>
                            <CircleCheck className="h-4 w-4" /> Complete
                          </Button>
                        )}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <Pagination page={page} size={20} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>

      <Modal open={modal?.kind === "new"} onClose={close} title="New statutory obligation">
        <ItemForm onDone={close} />
      </Modal>
      <Modal open={modal?.kind === "edit"} onClose={close} title="Edit obligation">
        {modal?.item && <ItemForm item={modal.item} onDone={close} />}
      </Modal>
      <Modal open={modal?.kind === "complete"} onClose={close} title="Record completion">
        {modal?.item && <CompleteForm item={modal.item} onDone={close} />}
      </Modal>
      <Modal open={modal?.kind === "view"} onClose={close} title="Obligation details" wide>
        {modal?.item && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="mr-auto text-lg font-semibold">{modal.item.title}</h3>
              <Badge tone={complianceTone[modal.item.status]}>{humanize(modal.item.status)}</Badge>
            </div>
            <KeyValue
              items={[
                { label: "Mine", value: modal.item.mine.name },
                { label: "Category", value: humanize(modal.item.category) },
                { label: "Statutory reference", value: modal.item.regulation_ref ?? "—" },
                { label: "Frequency", value: humanize(modal.item.frequency) },
                { label: "Due date", value: fmtDate(modal.item.due_date) },
                { label: "Owner", value: modal.item.owner?.full_name ?? "—" },
                { label: "Last completed", value: fmtDateTime(modal.item.last_completed_at) },
                { label: "Completion notes", value: modal.item.completion_notes ?? "—" },
              ]}
            />
            {modal.item.description && <p className="text-sm">{modal.item.description}</p>}
            <div>
              <h4 className="mb-3 text-sm font-semibold">Audit history</h4>
              <Timeline entity="compliance_item" id={modal.item.id} />
            </div>
            {writable && (
              <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
                <Button variant="ghost" className="text-bad" onClick={() => confirm("Delete this obligation?") && remove.mutate(modal.item!.id)} loading={remove.isPending}>
                  <Trash className="h-4 w-4" /> Delete
                </Button>
                <Button variant="outline" onClick={() => setModal({ kind: "edit", item: modal.item })}>
                  <Pencil className="h-4 w-4" /> Edit
                </Button>
                {modal.item.status !== "compliant" && (
                  <Button onClick={() => setModal({ kind: "complete", item: modal.item })}>
                    <CircleCheck className="h-4 w-4" /> Record completion
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

export default function CompliancePage() {
  return (
    <Suspense fallback={<Loading />}>
      <CompliancePageInner />
    </Suspense>
  );
}
