"use client";

import { useQuery } from "@tanstack/react-query";
import { Camera, Crosshair, ImagePlus, LoaderCircle, MapPin, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSession } from "@/components/session";
import { Badge, Button, Card, cn, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { getPosition, type QueuedPhoto } from "@/lib/offline";
import type { AuditEntry, Mine, Page, User } from "@/lib/types";

export function useMines() {
  return useQuery({
    queryKey: ["mines", "all"],
    queryFn: () => api<Page<Mine>>("/mines", { query: { size: 200 } }).then((p) => p.items),
    staleTime: 10 * 60_000,
  });
}

export function MineSelect({
  value,
  onChange,
  allowAll,
  required,
  id,
}: {
  value: string;
  onChange: (v: string) => void;
  allowAll?: boolean;
  required?: boolean;
  id?: string;
}) {
  const { data: mines = [] } = useMines();
  const { me } = useSession();
  // Mine officials are scoped to one mine: preselect it.
  useEffect(() => {
    if (!value && !allowAll && mines.length === 1) onChange(mines[0].id);
    else if (!value && !allowAll && me.mine_id && mines.some((m) => m.id === me.mine_id)) onChange(me.mine_id);
  }, [value, allowAll, mines, me.mine_id, onChange]);
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} required={required} aria-label="Mine">
      {allowAll ? <option value="">All mines</option> : <option value="">Select a mine…</option>}
      {mines.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name} ({m.code})
        </option>
      ))}
    </Select>
  );
}

export function UserSelect({
  value,
  onChange,
  mineId,
  id,
}: {
  value: string;
  onChange: (v: string) => void;
  mineId?: string;
  id?: string;
}) {
  const { data = [] } = useQuery({
    queryKey: ["users", "assignable", mineId],
    queryFn: () => api<Page<User>>("/users", { query: { size: 200, status: "active" } }).then((p) => p.items),
  });
  const users = data.filter((u) => u.role !== "regulator" && (!mineId || !u.mine_id || u.mine_id === mineId));
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} required aria-label="Assignee">
      <option value="">Select a person…</option>
      {users.map((u) => (
        <option key={u.id} value={u.id}>
          {u.full_name} — {humanize(u.role)}
          {u.mine ? ` (${u.mine.code})` : ""}
        </option>
      ))}
    </Select>
  );
}

export interface GeoValue {
  latitude: number;
  longitude: number;
  accuracy_m: number;
}

/** Captures the device GPS position for geo-tagged field reports. */
export function GeoCapture({ value, onChange, auto = true }: { value: GeoValue | null; onChange: (v: GeoValue | null) => void; auto?: boolean }) {
  const [state, setState] = useState<"idle" | "locating" | "denied">("idle");
  const locate = async () => {
    setState("locating");
    const pos = await getPosition();
    if (pos) {
      onChange(pos);
      setState("idle");
    } else setState("denied");
  };
  const started = useRef(false);
  useEffect(() => {
    if (auto && !value && !started.current) {
      started.current = true;
      void locate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto]);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-canvas px-3.5 py-2.5 text-sm">
      <MapPin className={cn("h-4 w-4", value ? "text-ok" : "text-muted")} />
      {value ? (
        <span className="tabular-nums">
          {value.latitude.toFixed(5)}, {value.longitude.toFixed(5)} <span className="text-muted">± {value.accuracy_m} m</span>
        </span>
      ) : state === "locating" ? (
        <span className="flex items-center gap-2 text-muted">
          <LoaderCircle className="h-4 w-4 animate-spin" /> Acquiring GPS…
        </span>
      ) : state === "denied" ? (
        <span className="text-warn">Location unavailable — allow location access for a verified geo-tag.</span>
      ) : (
        <span className="text-muted">No location captured</span>
      )}
      <Button type="button" size="sm" variant="outline" className="ml-auto" onClick={locate} loading={state === "locating"}>
        <Crosshair className="h-4 w-4" /> {value ? "Refresh" : "Capture"}
      </Button>
    </div>
  );
}

/** Camera/gallery capture that stamps each photo with the current geo-tag and time. */
export function PhotoCapture({
  photos,
  onChange,
  geo,
  max = 8,
}: {
  photos: QueuedPhoto[];
  onChange: (p: QueuedPhoto[]) => void;
  geo: GeoValue | null;
  max?: number;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const urls = useMemo(() => photos.map((p) => URL.createObjectURL(p.blob)), [photos]);
  useEffect(() => () => urls.forEach((x) => URL.revokeObjectURL(x)), [urls]);
  const add = (files: FileList | null) => {
    if (!files) return;
    const now = new Date().toISOString();
    const next = [...photos];
    for (const f of Array.from(files)) {
      if (next.length >= max) break;
      if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size > 20 * 1024 * 1024) continue;
      next.push({ blob: f, name: f.name || `photo-${Date.now()}.jpg`, latitude: geo?.latitude, longitude: geo?.longitude, captured_at: now });
    }
    onChange(next);
  };
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {urls.map((u, i) => (
          <div key={u} className="relative h-20 w-20 overflow-hidden rounded-xl border border-line">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={u} alt={`Evidence ${i + 1}`} className="h-full w-full object-cover" />
            <button
              type="button"
              onClick={() => onChange(photos.filter((_, j) => j !== i))}
              className="absolute top-1 right-1 rounded-full bg-black/60 p-0.5 text-white"
              aria-label="Remove photo"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        {photos.length < max && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="grid h-20 w-20 place-items-center rounded-xl border-2 border-dashed border-line text-muted hover:border-copper-400 hover:text-copper-400"
            aria-label="Add photo"
          >
            <span className="flex flex-col items-center gap-1 text-[11px]">
              <Camera className="h-5 w-5" /> Photo
            </span>
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        multiple
        className="hidden"
        onChange={(e) => {
          add(e.target.files);
          e.target.value = "";
        }}
      />
      <p className="mt-1.5 flex items-center gap-1 text-xs text-muted">
        <ImagePlus className="h-3.5 w-3.5" /> Photos are geo-tagged and time-stamped; they upload automatically when online.
      </p>
    </div>
  );
}

/** Uploads queued photos to an existing record (online path). */
export async function uploadPhotos(entity: string, id: string, photos: QueuedPhoto[]): Promise<number> {
  let ok = 0;
  for (const p of photos) {
    const form = new FormData();
    form.append("file", p.blob, p.name);
    if (p.latitude !== undefined) form.append("latitude", String(p.latitude));
    if (p.longitude !== undefined) form.append("longitude", String(p.longitude));
    form.append("captured_at", p.captured_at);
    try {
      await api(`/media/${entity}/${id}`, { method: "POST", form });
      ok += 1;
    } catch {
      /* reported by the caller via count */
    }
  }
  return ok;
}

export function MediaGallery({ entity, id }: { entity: string; id: string }) {
  const { data = [] } = useQuery({
    queryKey: ["media", entity, id],
    queryFn: () => api<{ id: string; filename: string; content_type: string; latitude: number | null; longitude: number | null; captured_at: string | null }[]>(`/media/${entity}/${id}`),
  });
  if (!data.length) return <p className="text-sm text-muted">No evidence uploaded.</p>;
  return (
    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {data.map((m) => (
        <li key={m.id}>
          <a href={`/api/files/media/${m.id}`} target="_blank" rel="noopener noreferrer" className="flex w-full items-center gap-3 rounded-xl border border-line px-3 py-2 text-left hover:bg-fg/5">
            <Camera className="h-4 w-4 text-copper-400" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{m.filename}</span>
              <span className="block text-xs text-muted">
                {m.captured_at ? fmtDateTime(m.captured_at) : "—"}
                {m.latitude !== null ? ` · ${m.latitude.toFixed(4)}, ${m.longitude?.toFixed(4)}` : ""}
              </span>
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/** History of one record, from the permanent audit log. */
export function Timeline({ entity, id }: { entity: string; id: string }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["timeline", entity, id],
    queryFn: () => api<AuditEntry[]>(`/audit/entity/${entity}/${id}`),
  });
  if (isLoading) return <p className="text-sm text-muted">Loading history…</p>;
  if (!data.length) return <p className="text-sm text-muted">History will appear once the audit trail records this item.</p>;
  return (
    <ol className="relative space-y-4 border-l border-line pl-5">
      {data.map((e) => (
        <li key={e.id} className="relative">
          <span className="absolute top-1.5 -left-[25px] h-2.5 w-2.5 rounded-full bg-copper-500 ring-4 ring-canvas" />
          <p className="text-sm font-medium">{humanize(e.action.split(".").slice(1).join(" ") || e.action)}</p>
          <p className="text-xs text-muted">
            {fmtDateTime(e.ts)} · {e.actor_name ?? "System"}
          </p>
        </li>
      ))}
    </ol>
  );
}

export function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  const { t } = useI18n();
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold">{t(title)}</h2>
        {action}
      </div>
      {children}
    </Card>
  );
}

export function GeoBadge({ verified, distance }: { verified: boolean; distance: number | null }) {
  if (distance === null) return <Badge tone="neutral">No geo-tag</Badge>;
  return verified ? (
    <Badge tone="ok">Geo-verified · {distance.toFixed(1)} km</Badge>
  ) : (
    <Badge tone="bad">Outside mine · {distance.toFixed(1)} km</Badge>
  );
}
