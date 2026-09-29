"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, Field, Input } from "@/components/ui";

export function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(token ? null : "This reset link is incomplete.");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pw !== confirm) return setError("Passwords do not match");
    setLoading(true);
    setError(null);
    const res = await fetch("/api/proxy/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: pw }),
    }).catch(() => null);
    setLoading(false);
    const data = res ? ((await res.json().catch(() => ({}))) as { detail?: string }) : {};
    if (!res || !res.ok) return setError(data.detail ?? "Reset failed");
    setDone(true);
  }

  if (done)
    return (
      <div className="py-6 text-center">
        <h1 className="text-2xl font-bold">Password updated</h1>
        <p className="mt-2 text-sm text-muted">All previous sessions were signed out.</p>
        <Link href="/login" className="mt-6 inline-block font-semibold text-copper-400 underline">
          Sign in
        </Link>
      </div>
    );

  return (
    <form onSubmit={submit} className="space-y-4">
      <h1 className="text-2xl font-bold">Choose a new password</h1>
      <Field label="New password" required hint="10+ characters with upper, lower, digit and symbol">
        <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required />
      </Field>
      <Field label="Confirm new password" required>
        <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
      </Field>
      {error && <p className="rounded-xl bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
      <Button type="submit" size="lg" className="w-full" loading={loading} disabled={!token || !pw}>
        Update password
      </Button>
    </form>
  );
}
