"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, CloudUpload, KeyRound, LogOut, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Section } from "@/components/common";
import { useSession } from "@/components/session";
import { Badge, Button, Field, Input, Select } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fromNow, roleLabel } from "@/lib/format";
import { clearFinished, listQueue, onQueueChange, syncNow, type QueuedEvent } from "@/lib/offline";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

function PushSetup() {
  const { data } = useQuery({ queryKey: ["vapid"], queryFn: () => api<{ enabled: boolean; public_key: string | null }>("/notifications/push/vapid-key") });
  const [state, setState] = useState<string>("");
  const enable = async () => {
    try {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) return setState("This browser does not support push notifications.");
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return setState("Permission was not granted.");
      const reg = (await navigator.serviceWorker.getRegistration()) ?? (await navigator.serviceWorker.register("/sw.js"));
      await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(data!.public_key!) as BufferSource });
      const json = sub.toJSON();
      await api("/notifications/push/subscribe", { body: { endpoint: json.endpoint, keys: json.keys } });
      setState("Push notifications enabled on this device.");
      await api("/notifications/test", { method: "POST" });
    } catch (e) {
      setState(errorMessage(e));
    }
  };
  if (!data?.enabled) return <p className="text-sm text-muted">Push notifications are not configured on the server (VAPID keys).</p>;
  return (
    <div className="space-y-2">
      <Button variant="outline" onClick={enable}><BellRing className="h-4 w-4" /> Enable push on this device</Button>
      {state && <p className="text-sm text-muted">{state}</p>}
    </div>
  );
}

function OfflineQueue() {
  const [items, setItems] = useState<QueuedEvent[]>([]);
  useEffect(() => {
    const refresh = () => void listQueue().then(setItems);
    refresh();
    return onQueueChange(refresh);
  }, []);
  const tone = { pending: "warn", sent: "info", uploading: "info", done: "ok", rejected: "bad" } as const;
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => void syncNow()}><CloudUpload className="h-4 w-4" /> Sync now</Button>
        <Button size="sm" variant="ghost" onClick={() => void clearFinished()}>Clear finished</Button>
      </div>
      {items.length ? (
        <ul className="divide-y divide-line text-sm">
          {items.map((i) => (
            <li key={i.client_event_id} className="flex items-center gap-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{i.label}</span>
                <span className="text-xs text-muted">{i.event_type} · {fromNow(i.created_at)}{i.photos.length ? ` · ${i.photos.length} photo(s) pending` : ""}{i.detail ? ` · ${i.detail}` : ""}</span>
              </span>
              <Badge tone={tone[i.state]}>{i.state}</Badge>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-muted">No field reports stored on this device.</p>}
    </div>
  );
}

export default function SettingsPage() {
  const { me } = useSession();
  const qc = useQueryClient();
  const [profile, setProfile] = useState({ full_name: me.full_name, phone: me.phone ?? "", designation: me.designation ?? "", preferred_language: me.preferred_language });
  const [prefs, setPrefs] = useState<Record<string, boolean>>({ email: true, sms: false, push: true, ...me.notification_prefs });
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const saveProfile = useMutation({
    mutationFn: () => api("/auth/me", { method: "PATCH", body: { ...profile, phone: profile.phone || null, designation: profile.designation || null, notification_prefs: prefs } }),
    onSuccess: () => { toast.success("Settings saved"); void qc.invalidateQueries({ queryKey: ["me"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const changePw = useMutation({
    mutationFn: () => {
      if (pw.next !== pw.confirm) throw new Error("New passwords do not match");
      return api("/auth/change-password", { body: { current_password: pw.current, new_password: pw.next } });
    },
    onSuccess: () => { toast.success("Password changed — other sessions signed out"); setPw({ current: "", next: "", confirm: "" }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const logoutAll = async () => {
    await api("/auth/logout-all", { method: "POST" }).catch(() => undefined);
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  };
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted">{roleLabel[me.role]}{me.mine ? ` · ${me.mine.name}` : me.subsidiary_name ? ` · ${me.subsidiary_name}` : ""} · {me.email}</p>
      </div>
      <Section title="Profile & preferences">
        <form onSubmit={(e) => { e.preventDefault(); saveProfile.mutate(); }} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Full name"><Input value={profile.full_name} onChange={(e) => setProfile((p) => ({ ...p, full_name: e.target.value }))} /></Field>
            <Field label="Designation"><Input value={profile.designation} onChange={(e) => setProfile((p) => ({ ...p, designation: e.target.value }))} /></Field>
            <Field label="Mobile (for SMS alerts)"><Input value={profile.phone} onChange={(e) => setProfile((p) => ({ ...p, phone: e.target.value }))} /></Field>
            <Field label="Preferred language">
              <Select value={profile.preferred_language} onChange={(e) => setProfile((p) => ({ ...p, preferred_language: e.target.value }))}>
                <option value="en">English</option><option value="hi">हिन्दी</option><option value="bn">বাংলা</option><option value="or">ଓଡ଼ିଆ</option><option value="te">తెలుగు</option><option value="mr">मराठी</option><option value="ta">தமிழ்</option>
              </Select>
            </Field>
          </div>
          <fieldset className="flex flex-wrap gap-5 text-sm">
            <legend className="mb-2 text-sm font-medium">Alert channels (warnings & critical)</legend>
            {(["email", "sms", "push"] as const).map((k) => (
              <label key={k} className="flex items-center gap-2">
                <input type="checkbox" className="accent-copper-700" checked={!!prefs[k]} onChange={(e) => setPrefs((p) => ({ ...p, [k]: e.target.checked }))} />
                {k === "sms" ? "SMS" : k[0].toUpperCase() + k.slice(1)}
              </label>
            ))}
          </fieldset>
          <Button type="submit" loading={saveProfile.isPending}><Save className="h-4 w-4" /> Save</Button>
        </form>
      </Section>
      <Section title="Push notifications"><PushSetup /></Section>
      <Section title="Offline field reports on this device"><OfflineQueue /></Section>
      <Section title="Security">
        <form onSubmit={(e) => { e.preventDefault(); changePw.mutate(); }} className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Current password"><Input type="password" value={pw.current} onChange={(e) => setPw((p) => ({ ...p, current: e.target.value }))} autoComplete="current-password" /></Field>
          <Field label="New password"><Input type="password" value={pw.next} onChange={(e) => setPw((p) => ({ ...p, next: e.target.value }))} autoComplete="new-password" /></Field>
          <Field label="Confirm"><Input type="password" value={pw.confirm} onChange={(e) => setPw((p) => ({ ...p, confirm: e.target.value }))} autoComplete="new-password" /></Field>
          <div className="flex flex-wrap gap-2 sm:col-span-3">
            <Button type="submit" loading={changePw.isPending} disabled={!pw.current || !pw.next}><KeyRound className="h-4 w-4" /> Change password</Button>
            <Button type="button" variant="outline" onClick={logoutAll}><LogOut className="h-4 w-4" /> Sign out of all devices</Button>
          </div>
        </form>
      </Section>
    </div>
  );
}
