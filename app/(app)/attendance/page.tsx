"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { UserCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { GeoCapture, MineSelect, type GeoValue } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { fmtDateTime, uuid } from "@/lib/format";
import { enqueue } from "@/lib/offline";
import type { Attendance, Contractor, Page } from "@/lib/types";

export default function AttendancePage() {
  const { can } = useSession();
  const qc = useQueryClient();
  const [mineFilter, setMineFilter] = useState("");
  const [page, setPage] = useState(1);
  const [form, setForm] = useState({ mine_id: "", worker_name: "", worker_id_no: "", contractor_id: "", shift: "A" });
  const [geo, setGeo] = useState<GeoValue | null>(null);
  const [saving, setSaving] = useState(false);
  const { data: contractors } = useQuery({ queryKey: ["contractors", "picker"], queryFn: () => api<Page<Contractor>>("/contractors", { query: { size: 200 } }) });
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["attendance", mineFilter, page],
    queryFn: () => api<Page<Attendance>>("/attendance", { query: { mine_id: mineFilter, page, size: 25 } }),
  });
  const contractorName = (id: string | null) => contractors?.items.find((c) => c.id === id)?.name ?? "Departmental";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    const cid = uuid();
    const payload = {
      mine_id: form.mine_id, worker_name: form.worker_name, worker_id_no: form.worker_id_no || null,
      contractor_id: form.contractor_id || null, shift: form.shift, geo, check_in_at: new Date().toISOString(),
    };
    try {
      if (!navigator.onLine) {
        await enqueue("attendance.logged", payload, `Attendance: ${form.worker_name}`, [], cid);
        toast.success("Saved offline — will sync automatically");
      } else {
        const rec = await api<Attendance>("/attendance", { body: { ...payload, client_event_id: cid } });
        toast.success(rec.geo_verified ? "Attendance recorded (geo-verified)" : "Recorded — location outside mine boundary");
        void qc.invalidateQueries({ queryKey: ["attendance"] });
      }
      setForm((f) => ({ ...f, worker_name: "", worker_id_no: "" }));
    } catch (err) {
      if (!(err instanceof ApiError)) {
        await enqueue("attendance.logged", payload, `Attendance: ${form.worker_name}`, [], cid);
        toast.success("Saved offline — will sync automatically");
      } else toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Attendance" subtitle="Record who is on site each shift — works without internet" />
      {can("attendance:write") && (
        <Card>
          <CardHeader title="Log check-in" subtitle="Works offline" />
          <form onSubmit={submit} className="grid grid-cols-1 gap-4 px-5 pb-5 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Mine" required><MineSelect value={form.mine_id} onChange={(v) => setForm((f) => ({ ...f, mine_id: v }))} required /></Field>
            <Field label="Worker name" required><Input value={form.worker_name} onChange={(e) => setForm((f) => ({ ...f, worker_name: e.target.value }))} required minLength={2} /></Field>
            <Field label="Worker ID / Form-B no." hint="Stored encrypted"><Input value={form.worker_id_no} onChange={(e) => setForm((f) => ({ ...f, worker_id_no: e.target.value }))} /></Field>
            <Field label="Employer">
              <Select value={form.contractor_id} onChange={(e) => setForm((f) => ({ ...f, contractor_id: e.target.value }))}>
                <option value="">Departmental</option>
                {contractors?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </Field>
            <Field label="Shift" required>
              <Select value={form.shift} onChange={(e) => setForm((f) => ({ ...f, shift: e.target.value }))}>
                {["A", "B", "C", "general"].map((s) => <option key={s} value={s}>{s === "general" ? "General" : `Shift ${s}`}</option>)}
              </Select>
            </Field>
            <div className="sm:col-span-2 lg:col-span-3"><GeoCapture value={geo} onChange={setGeo} /></div>
            <div className="sm:col-span-2 lg:col-span-3 flex justify-end">
              <Button type="submit" loading={saving} disabled={!form.mine_id || !form.worker_name}><UserCheck className="h-4 w-4" /> Record check-in</Button>
            </div>
          </form>
        </Card>
      )}
      <Card>
        <div className="flex items-center gap-3 border-b border-line p-4">
          <div className="w-full sm:w-80"><MineSelect allowAll value={mineFilter} onChange={(v) => { setMineFilter(v); setPage(1); }} /></div>
        </div>
        {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
          <EmptyState icon={<UserCheck className="h-6 w-6" />} title="No attendance records" />
        ) : (
          <>
            <Table>
              <thead><tr><Th>Worker</Th><Th>Employer</Th><Th>Shift</Th><Th>Check-in</Th><Th>Location</Th><Th>Source</Th></tr></thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <Td className="font-medium">{a.worker_name}</Td>
                    <Td>{contractorName(a.contractor_id)}</Td>
                    <Td>{a.shift}</Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(a.check_in_at)}</Td>
                    <Td>{a.latitude === null ? <Badge tone="neutral">None</Badge> : a.geo_verified ? <Badge tone="ok">Verified</Badge> : <Badge tone="bad">Outside</Badge>}</Td>
                    <Td className="capitalize">{a.source}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} size={25} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
