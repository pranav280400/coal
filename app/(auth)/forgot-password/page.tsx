"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, Input } from "@/components/ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const res = await fetch("/api/proxy/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }).catch(() => null);
    setLoading(false);
    const data = res ? ((await res.json().catch(() => ({}))) as { detail?: string }) : {};
    if (!res || !res.ok) return setError(data.detail ?? "Request failed");
    setMsg(data.detail ?? "If the email is registered, a reset link has been sent.");
  }

  return (
    <AuthFrame>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold">Reset your password</h1>
          <p className="mt-1 text-sm text-muted">We will email a single-use link valid for 30 minutes.</p>
        </div>
        <Field label="Registered email" required>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </Field>
        {msg && <p className="rounded-xl bg-ok-soft px-3 py-2 text-sm text-ok">{msg}</p>}
        {error && <p className="rounded-xl bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
        <Button type="submit" size="lg" className="w-full" loading={loading} disabled={!email}>
          Send reset link
        </Button>
        <p className="text-center text-sm">
          <Link href="/login" className="font-semibold text-copper-400 underline">
            Back to sign in
          </Link>
        </p>
      </form>
    </AuthFrame>
  );
}
