"use client";

import { CircleCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AuthFrame } from "@/components/auth-frame";
import { Button, Field, Input, Select, Textarea } from "@/components/ui";

export default function RegisterPage() {
  const [form, setForm] = useState({
    full_name: "",
    username: "",
    email: "",
    phone: "",
    designation: "",
    requested_role: "mine_official",
    mine_code: "",
    note: "",
    password: "",
    confirm: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (form.password !== form.confirm) return setError("Passwords do not match");
    setLoading(true);
    setError(null);
    const { full_name, username, email, phone, designation, requested_role, mine_code, note, password } = form;
    const body = { full_name, username, email, phone, designation, requested_role, mine_code, note, password };
    const res = await fetch("/api/proxy/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...body,
        phone: body.phone || null,
        designation: body.designation || null,
        mine_code: body.mine_code || null,
        note: body.note || null,
      }),
    }).catch(() => null);
    setLoading(false);
    if (!res) return setError("Cannot reach the server");
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { detail?: string; errors?: { loc: string[]; msg: string }[] };
      return setError(data.errors?.[0] ? `${data.errors[0].loc.at(-1)}: ${data.errors[0].msg}` : data.detail ?? "Request failed");
    }
    setDone(true);
  }

  return (
    <AuthFrame>
      {done ? (
        <div className="py-6 text-center">
          <CircleCheck className="mx-auto h-12 w-12 text-ok" />
          <h1 className="mt-4 text-2xl font-bold">Request submitted</h1>
          <p className="mt-2 text-sm text-muted">
            An administrator will verify your details and activate your account. You will be notified by email.
          </p>
          <Link href="/login" className="mt-6 inline-block font-semibold text-copper-400 underline">
            Back to sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3.5">
          <div>
            <h1 className="text-2xl font-bold">Request access</h1>
            <p className="mt-1 text-sm text-muted">Accounts are activated after verification by an administrator.</p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Full name" required>
              <Input value={form.full_name} onChange={set("full_name")} required autoComplete="name" />
            </Field>
            <Field label="Username" required hint="3–64 letters, digits, . _ -">
              <Input value={form.username} onChange={set("username")} required autoComplete="username" pattern="[a-zA-Z0-9._-]{3,64}" />
            </Field>
            <Field label="Official email" required>
              <Input type="email" value={form.email} onChange={set("email")} required autoComplete="email" />
            </Field>
            <Field label="Mobile">
              <Input value={form.phone} onChange={set("phone")} placeholder="+91…" autoComplete="tel" />
            </Field>
            <Field label="Role requested" required>
              <Select value={form.requested_role} onChange={set("requested_role")}>
                <option value="mine_official">Mine Official</option>
                <option value="corporate">Corporate Management</option>
                <option value="regulator">Regulator</option>
                <option value="contractor">Contractor</option>
              </Select>
            </Field>
            <Field label="Mine code" hint="e.g. MCL-KLG (for mine officials)">
              <Input value={form.mine_code} onChange={set("mine_code")} />
            </Field>
            <Field label="Designation">
              <Input value={form.designation} onChange={set("designation")} />
            </Field>
            <div />
            <Field label="Password" required hint="10+ chars, upper, lower, digit, symbol">
              <Input type="password" value={form.password} onChange={set("password")} required autoComplete="new-password" />
            </Field>
            <Field label="Confirm password" required>
              <Input type="password" value={form.confirm} onChange={set("confirm")} required autoComplete="new-password" />
            </Field>
          </div>
          <Field label="Note for the administrator">
            <Textarea value={form.note} onChange={set("note")} className="min-h-16" placeholder="Employee ID, reporting officer…" />
          </Field>
          {error && <p className="rounded-xl bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
          <Button type="submit" className="w-full" size="lg" loading={loading}>
            Submit request
          </Button>
          <p className="text-center text-sm text-muted">
            Already registered?{" "}
            <Link href="/login" className="font-semibold text-copper-400 underline">
              Sign in
            </Link>
          </p>
        </form>
      )}
    </AuthFrame>
  );
}
