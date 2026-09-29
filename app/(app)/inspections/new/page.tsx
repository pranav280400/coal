"use client";

import { Check, CloudUpload, Plus, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { GeoCapture, MineSelect, PhotoCapture, uploadPhotos, type GeoValue } from "@/components/common";
import { Button, Card, cn, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { humanize, uuid } from "@/lib/format";
import { enqueue, type QueuedPhoto } from "@/lib/offline";
import type { ChecklistItem, Inspection, InspectionType } from "@/lib/types";

const TEMPLATES: Record<InspectionType, string[]> = {
  routine: ["Haul roads & berms as per traffic rules", "PPE compliance of all persons", "Dust suppression operational", "HEMM brakes, alarms & proximity devices", "Statutory registers up to date"],
  safety: ["Bench height/width & slope stability", "Roof & side support (underground)", "Ventilation & gas monitoring", "Fire-fighting equipment serviceable", "Electrical earthing & protection", "Emergency escape routes clear"],
  environmental: ["Fog cannons / sprinklers operating", "Mine water treated before discharge", "Overburden dump stability & plantation", "Ambient air monitoring station working", "Noise levels within limits"],
  compliance_audit: ["Statutory returns filed on time", "Consents (CTO/EC) valid", "Contract labour licences valid", "Medical examinations up to date", "Vocational training records"],
  statutory: ["Manager's diary & shift reports", "Accident/dangerous occurrence register", "Mine plans & sections updated", "Blasting records", "Inspection book compliance"],
  reinspection: ["Corrective action implemented as submitted", "Evidence matches site condition", "No recurrence observed"],
};

export default function NewInspectionPage() {
  const router = useRouter();
  const [mineId, setMineId] = useState("");
  const [type, setType] = useState<InspectionType>("routine");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [checklist, setChecklist] = useState<ChecklistItem[]>(TEMPLATES.routine.map((item) => ({ item, passed: true, note: "" })));
  const [custom, setCustom] = useState("");
  const [geo, setGeo] = useState<GeoValue | null>(null);
  const [photos, setPhotos] = useState<QueuedPhoto[]>([]);
  const [saving, setSaving] = useState(false);

  const changeType = (t: InspectionType) => {
    setType(t);
    setChecklist(TEMPLATES[t].map((item) => ({ item, passed: true, note: "" })));
  };
  const failed = checklist.filter((c) => !c.passed).length;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!mineId) return toast.error("Select a mine");
    setSaving(true);
    const clientEventId = uuid();
    const payload = {
      mine_id: mineId,
      inspection_type: type,
      title: title || `${humanize(type)} inspection`,
      notes,
      checklist: checklist.map((c) => ({ item: c.item, passed: c.passed, note: c.note || null })),
      geo,
      inspected_at: new Date().toISOString(),
    };
    const queueOffline = async () => {
      await enqueue("inspection.submitted", payload, payload.title, photos, clientEventId);
      toast.success("Saved offline — it will sync automatically when you are back online.");
      router.push("/inspections");
    };
    try {
      if (!navigator.onLine) return await queueOffline();
      const created = await api<Inspection>("/inspections", { body: { ...payload, client_event_id: clientEventId } });
      if (photos.length) {
        const n = await uploadPhotos("inspection", created.id, photos);
        if (n < photos.length) toast.warning(`${photos.length - n} photo(s) failed to upload`);
      }
      toast.success(
        created.geo_verified || !geo ? "Inspection submitted — AI analysis running" : "Submitted, but the geo-tag is outside the mine boundary",
      );
      router.push(`/inspections/${created.id}`);
    } catch (err) {
      // Network failure → keep the work: queue with the same idempotent id semantics.
      if (!(err instanceof ApiError)) await queueOffline();
      else toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl space-y-5">
      <PageHeader title="New inspection" subtitle="Works offline: reports are queued on this device and synced on reconnect" />
      <Card className="space-y-4 p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Mine" required>
            <MineSelect value={mineId} onChange={setMineId} required />
          </Field>
          <Field label="Inspection type" required>
            <Select value={type} onChange={(e) => changeType(e.target.value as InspectionType)}>
              {Object.keys(TEMPLATES).map((t) => (
                <option key={t} value={t}>{humanize(t)}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Title">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`${humanize(type)} inspection`} />
        </Field>
        <Field label="Location (geo-tag)" hint="Verified against the mine lease boundary">
          <GeoCapture value={geo} onChange={setGeo} />
        </Field>
      </Card>

      <Card className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Checklist</h2>
          <span className={cn("text-sm font-medium", failed ? "text-bad" : "text-ok")}>
            {failed ? `${failed} deficienc${failed > 1 ? "ies" : "y"}` : "All items compliant"}
          </span>
        </div>
        <ul className="space-y-2">
          {checklist.map((c, i) => (
            <li key={`${c.item}-${i}`} className={cn("rounded-xl border p-3", c.passed ? "border-line" : "border-bad/40 bg-bad-soft/40")}>
              <div className="flex items-center gap-3">
                <span className="flex-1 text-sm">{c.item}</span>
                <div className="flex overflow-hidden rounded-lg border border-line text-xs font-semibold">
                  <button type="button" onClick={() => setChecklist((l) => l.map((x, j) => (j === i ? { ...x, passed: true } : x)))}
                    className={cn("flex items-center gap-1 px-2.5 py-1.5", c.passed ? "bg-ok text-white" : "bg-surface text-muted")} aria-pressed={c.passed}>
                    <Check className="h-3.5 w-3.5" /> OK
                  </button>
                  <button type="button" onClick={() => setChecklist((l) => l.map((x, j) => (j === i ? { ...x, passed: false } : x)))}
                    className={cn("flex items-center gap-1 px-2.5 py-1.5", !c.passed ? "bg-bad text-white" : "bg-surface text-muted")} aria-pressed={!c.passed}>
                    <X className="h-3.5 w-3.5" /> Issue
                  </button>
                </div>
              </div>
              {!c.passed && (
                <Input className="mt-2" placeholder="Describe the deficiency…" value={c.note ?? ""}
                  onChange={(e) => setChecklist((l) => l.map((x, j) => (j === i ? { ...x, note: e.target.value } : x)))} />
              )}
            </li>
          ))}
        </ul>
        <div className="mt-3 flex gap-2">
          <Input placeholder="Add a checklist item…" value={custom} onChange={(e) => setCustom(e.target.value)} />
          <Button type="button" variant="outline" disabled={!custom.trim()}
            onClick={() => { setChecklist((l) => [...l, { item: custom.trim(), passed: true, note: "" }]); setCustom(""); }}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <Field label="Observations & notes" hint="English or Hindi — the AI summary handles both">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="min-h-32" />
        </Field>
        <Field label="Photo evidence">
          <PhotoCapture photos={photos} onChange={setPhotos} geo={geo} />
        </Field>
      </Card>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => router.back()}>Cancel</Button>
        <Button type="submit" size="lg" loading={saving}>
          <CloudUpload className="h-4 w-4" /> Submit inspection
        </Button>
      </div>
    </form>
  );
}
