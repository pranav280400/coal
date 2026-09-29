"use client";

import { useQuery } from "@tanstack/react-query";
import { CloudUpload } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { GeoCapture, MineSelect, PhotoCapture, uploadPhotos, type GeoValue } from "@/components/common";
import { useSession } from "@/components/session";
import { Button, Card, Field, Input, Loading, PageHeader, Select, Textarea } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { humanize, uuid } from "@/lib/format";
import { enqueue, type QueuedPhoto } from "@/lib/offline";
import type { Contractor, Page, Violation } from "@/lib/types";

function NewViolationForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { can } = useSession();
  const [form, setForm] = useState({
    mine_id: params.get("mine_id") ?? "",
    inspection_id: params.get("inspection_id") ?? "",
    contractor_id: "",
    kind: "violation",
    category: "safety",
    title: "",
    description: "",
    severity: "",
    regulation_ref: "",
  });
  const [geo, setGeo] = useState<GeoValue | null>(null);
  const [photos, setPhotos] = useState<QueuedPhoto[]>([]);
  const [saving, setSaving] = useState(false);
  const { data: contractors } = useQuery({
    queryKey: ["contractors", "picker"],
    queryFn: () => api<Page<Contractor>>("/contractors", { query: { size: 200 } }),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.mine_id) return toast.error("Select a mine");
    setSaving(true);
    const clientEventId = uuid();
    const payload = {
      mine_id: form.mine_id,
      inspection_id: form.inspection_id || null,
      contractor_id: form.contractor_id || null,
      kind: form.kind,
      category: form.category,
      title: form.title,
      description: form.description,
      severity: form.severity || null,
      regulation_ref: form.regulation_ref || null,
      geo,
      occurred_at: new Date().toISOString(),
    };
    const offline = async () => {
      await enqueue("violation.reported", payload, form.title, photos, clientEventId);
      toast.success("Saved offline — it will sync automatically.");
      router.push("/violations");
    };
    try {
      if (!navigator.onLine) return await offline();
      const v = await api<Violation>("/violations", { body: { ...payload, client_event_id: clientEventId } });
      if (photos.length) await uploadPhotos("violation", v.id, photos);
      toast.success(
        form.severity ? "Violation reported" : `Reported — AI suggests ${humanize(v.ai_suggested_severity ?? v.severity)} severity (pending confirmation)`,
      );
      router.push(`/violations/${v.id}`);
    } catch (err) {
      if (!(err instanceof ApiError)) await offline();
      else toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl space-y-5">
      <PageHeader title="Report a violation" subtitle="Safety observations, statutory violations and incidents — works offline" />
      <Card className="space-y-4 p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Mine" required>
            <MineSelect value={form.mine_id} onChange={(v) => setForm((f) => ({ ...f, mine_id: v }))} required />
          </Field>
          <Field label="Type" required>
            <Select value={form.kind} onChange={set("kind")}>
              <option value="violation">Statutory violation</option>
              <option value="safety_observation">Safety observation</option>
              <option value="incident">Incident / dangerous occurrence</option>
            </Select>
          </Field>
          <Field label="Category" required>
            <Select value={form.category} onChange={set("category")}>
              {["safety", "environment", "production", "labour"].map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
            </Select>
          </Field>
          <Field label="Severity" hint={can("violation:confirm") ? "Leave blank to let AI suggest one" : "AI suggests; an official confirms"}>
            <Select value={form.severity} onChange={set("severity")}>
              <option value="">AI suggestion</option>
              {["critical", "high", "medium", "low"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Title" required>
          <Input value={form.title} onChange={set("title")} required minLength={3} placeholder="e.g. Dumper operating without reversing alarm" />
        </Field>
        <Field label="Description" required hint="English, Hindi or Odia are all fine">
          <Textarea value={form.description} onChange={set("description")} required minLength={5} className="min-h-32" />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Contractor involved">
            <Select value={form.contractor_id} onChange={set("contractor_id")}>
              <option value="">— none —</option>
              {contractors?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label="Statutory reference">
            <Input value={form.regulation_ref} onChange={set("regulation_ref")} placeholder="e.g. CMR 2017 Reg. 196" />
          </Field>
        </div>
        <Field label="Location">
          <GeoCapture value={geo} onChange={setGeo} />
        </Field>
        <Field label="Photo evidence">
          <PhotoCapture photos={photos} onChange={setPhotos} geo={geo} />
        </Field>
      </Card>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => router.back()}>Cancel</Button>
        <Button type="submit" size="lg" loading={saving}>
          <CloudUpload className="h-4 w-4" /> Submit
        </Button>
      </div>
    </form>
  );
}

export default function NewViolationPage() {
  return (
    <Suspense fallback={<Loading />}>
      <NewViolationForm />
    </Suspense>
  );
}
