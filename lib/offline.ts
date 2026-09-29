"use client";

import { openDB, type DBSchema, type IDBPDatabase } from "idb";
import { buildUrl } from "@/lib/api";
import { uuid } from "@/lib/format";

// Offline-first field capture (FR4 / NFR offline resilience).
//
// Every field submission is written to IndexedDB first with an idempotent
// client_event_id, then synced to POST /ingest/events (→ Kafka). Photos stay in
// IndexedDB until the server confirms which record they belong to, then upload to
// /media/<entity>/<id>. Retries can never create duplicates server-side.

export type FieldEventType = "inspection.submitted" | "violation.reported" | "attendance.logged";

export interface QueuedPhoto {
  blob: Blob;
  name: string;
  latitude?: number;
  longitude?: number;
  captured_at: string;
}

export interface QueuedEvent {
  client_event_id: string;
  event_type: FieldEventType;
  captured_at: string;
  payload: Record<string, unknown>;
  photos: QueuedPhoto[];
  state: "pending" | "sent" | "uploading" | "done" | "rejected";
  entity_type?: string;
  entity_id?: string;
  detail?: string;
  attempts: number;
  created_at: string;
  label: string;
}

interface OfflineDB extends DBSchema {
  events: { key: string; value: QueuedEvent; indexes: { state: string } };
}

let dbPromise: Promise<IDBPDatabase<OfflineDB>> | null = null;

function db() {
  dbPromise ??= openDB<OfflineDB>("coalminegov-offline", 1, {
    upgrade(database) {
      const store = database.createObjectStore("events", { keyPath: "client_event_id" });
      store.createIndex("state", "state");
    },
  });
  return dbPromise;
}

const listeners = new Set<() => void>();
export function onQueueChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function emit() {
  listeners.forEach((fn) => fn());
}

export async function enqueue(
  event_type: FieldEventType,
  payload: Record<string, unknown>,
  label: string,
  photos: QueuedPhoto[] = [],
  clientEventId?: string,
): Promise<QueuedEvent> {
  const item: QueuedEvent = {
    // Reuse the id of a failed online attempt so a request that did reach the server is deduplicated.
    client_event_id: clientEventId ?? uuid(),
    event_type,
    captured_at: new Date().toISOString(),
    payload,
    photos,
    state: "pending",
    attempts: 0,
    created_at: new Date().toISOString(),
    label,
  };
  await (await db()).put("events", item);
  emit();
  // Ask the service worker to wake us via Background Sync when connectivity returns
  // (supported on Chromium/Android); the online/visibility/interval triggers cover others.
  navigator.serviceWorker?.ready
    .then((reg) => (reg as ServiceWorkerRegistration & { sync?: { register(tag: string): Promise<void> } }).sync?.register("cmg-sync"))
    .catch(() => undefined);
  void syncNow();
  return item;
}

export async function listQueue(): Promise<QueuedEvent[]> {
  const all = await (await db()).getAll("events");
  return all.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export async function pendingCount(): Promise<number> {
  const all = await (await db()).getAll("events");
  return all.filter((e) => e.state !== "done" && e.state !== "rejected").length;
}

export async function clearFinished(): Promise<void> {
  const database = await db();
  for (const e of await database.getAll("events")) {
    if (e.state === "done" || e.state === "rejected") await database.delete("events", e.client_event_id);
  }
  emit();
}

let syncing = false;

/** Push pending events, resolve server ids, upload photos. Safe to call repeatedly. */
export async function syncNow(): Promise<void> {
  if (syncing || typeof navigator === "undefined" || !navigator.onLine) return;
  syncing = true;
  try {
    const database = await db();
    const pending = (await database.getAll("events")).filter((e) => e.state === "pending");
    if (pending.length) {
      const res = await fetch(buildUrl("/ingest/events"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: deviceId(),
          events: pending.map(({ client_event_id, event_type, captured_at, payload }) => ({
            client_event_id,
            event_type,
            captured_at,
            payload,
          })),
        }),
      });
      if (res.ok) {
        const { results } = (await res.json()) as {
          results: { client_event_id: string; status: string; detail?: string }[];
        };
        for (const r of results) {
          const item = await database.get("events", r.client_event_id);
          if (!item) continue;
          item.attempts += 1;
          if (r.status === "rejected") {
            item.state = "rejected";
            item.detail = r.detail;
          } else {
            item.state = "sent";
          }
          await database.put("events", item);
        }
        emit();
      }
    }
    await resolveAndUpload(database);
  } catch {
    // Network dropped mid-sync: everything stays queued and is retried later.
  } finally {
    syncing = false;
  }
}

async function resolveAndUpload(database: IDBPDatabase<OfflineDB>) {
  const sent = (await database.getAll("events")).filter((e) => e.state === "sent" || e.state === "uploading");
  if (!sent.length) return;
  const res = await fetch(buildUrl("/ingest/status", { ids: sent.map((e) => e.client_event_id) }));
  if (!res.ok) return;
  const statuses = (await res.json()) as Record<string, { status: string; entity_type?: string; entity_id?: string; detail?: string }>;
  for (const item of sent) {
    const st = statuses[item.client_event_id];
    if (!st || st.status === "queued") continue;
    if (st.status === "rejected") {
      item.state = "rejected";
      item.detail = st.detail;
      await database.put("events", item);
      continue;
    }
    item.entity_type = st.entity_type;
    item.entity_id = st.entity_id;
    item.state = "uploading";
    await database.put("events", item);
    const remaining: QueuedPhoto[] = [];
    for (const photo of item.photos) {
      if (!item.entity_type || item.entity_type === "attendance") continue;
      const form = new FormData();
      form.append("file", photo.blob, photo.name);
      if (photo.latitude !== undefined) form.append("latitude", String(photo.latitude));
      if (photo.longitude !== undefined) form.append("longitude", String(photo.longitude));
      form.append("captured_at", photo.captured_at);
      const up = await fetch(buildUrl(`/media/${item.entity_type}/${item.entity_id}`), { method: "POST", body: form });
      if (!up.ok && up.status >= 500) remaining.push(photo);
    }
    item.photos = remaining;
    item.state = remaining.length ? "uploading" : "done";
    await database.put("events", item);
  }
  emit();
}

function deviceId(): string {
  try {
    let id = localStorage.getItem("cmg-device-id");
    if (!id) {
      id = `web-${uuid().slice(0, 16)}`;
      localStorage.setItem("cmg-device-id", id);
    }
    return id;
  } catch {
    return "web-unknown";
  }
}

/** Current position with a timeout; resolves null if denied/unavailable. */
export function getPosition(timeoutMs = 12_000): Promise<{ latitude: number; longitude: number; accuracy_m: number } | null> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: Number(pos.coords.latitude.toFixed(6)),
          longitude: Number(pos.coords.longitude.toFixed(6)),
          accuracy_m: Math.round(pos.coords.accuracy),
        }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 30_000 },
    );
  });
}

let started = false;
/** Start background sync: on reconnect, on an interval, and when the tab regains focus. */
export function startAutoSync(): void {
  if (started || typeof window === "undefined") return;
  started = true;
  window.addEventListener("online", () => void syncNow());
  navigator.serviceWorker?.addEventListener("message", (e) => e.data === "cmg-sync" && void syncNow());
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && void syncNow());
  setInterval(() => void syncNow(), 20_000);
  void syncNow();
}
