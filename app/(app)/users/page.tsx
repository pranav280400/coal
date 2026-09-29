"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Users } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { MineSelect } from "@/components/common";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, humanize, roleLabel } from "@/lib/format";
import type { Contractor, Page, Role, Subsidiary, User } from "@/lib/types";

const ROLES: Role[] = ["admin", "corporate", "mine_official", "regulator", "contractor"];

function UserForm({ user, onDone }: { user?: User; onDone: () => void }) {
  const qc = useQueryClient();
  const { data: subs = [] } = useQuery({ queryKey: ["subsidiaries"], queryFn: () => api<Subsidiary[]>("/subsidiaries") });
  const { data: contractors } = useQuery({ queryKey: ["contractors", "picker"], queryFn: () => api<Page<Contractor>>("/contractors", { query: { size: 200 } }) });
  const [f, setF] = useState({
    username: user?.username ?? "", email: user?.email ?? "", full_name: user?.full_name ?? "", designation: user?.designation ?? "",
    phone: user?.phone ?? "", password: "", role: user?.role ?? ("mine_official" as Role), status: user?.status ?? "active",
    subsidiary_id: user?.subsidiary_id ?? "", mine_id: user?.mine_id ?? "", contractor_id: user?.contractor_id ?? "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }));
  const links = {
    subsidiary_id: f.role === "corporate" ? f.subsidiary_id || null : null,
    mine_id: f.role === "mine_official" ? f.mine_id || null : null,
    contractor_id: f.role === "contractor" ? f.contractor_id || null : null,
  };
  const save = useMutation({
    mutationFn: () =>
      user
        ? api(`/users/${user.id}`, { method: "PATCH", body: { full_name: f.full_name, designation: f.designation || null, phone: f.phone || null, role: f.role, status: f.status, ...links } })
        : api("/users", { body: { username: f.username, email: f.email, full_name: f.full_name, designation: f.designation || null, phone: f.phone || null, password: f.password, role: f.role, ...links } }),
    onSuccess: () => { toast.success(user ? "User updated" : "User created"); void qc.invalidateQueries({ queryKey: ["users"] }); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {!user && <Field label="Username" required><Input value={f.username} onChange={set("username")} required /></Field>}
        {!user && <Field label="Email" required><Input type="email" value={f.email} onChange={set("email")} required /></Field>}
        <Field label="Full name" required><Input value={f.full_name} onChange={set("full_name")} required /></Field>
        <Field label="Designation"><Input value={f.designation} onChange={set("designation")} /></Field>
        <Field label="Mobile"><Input value={f.phone} onChange={set("phone")} /></Field>
        <Field label="Role" required>
          <Select value={f.role} onChange={set("role")}>{ROLES.map((r) => <option key={r} value={r}>{roleLabel[r]}</option>)}</Select>
        </Field>
        {user && (
          <Field label="Status">
            <Select value={f.status} onChange={set("status")}>{["pending", "active", "disabled"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</Select>
          </Field>
        )}
        {!user && <Field label="Initial password" required hint="User should change it after first sign-in"><Input type="password" value={f.password} onChange={set("password")} required autoComplete="new-password" /></Field>}
      </div>
      {f.role === "mine_official" && <Field label="Mine" required><MineSelect value={f.mine_id} onChange={(v) => setF((s) => ({ ...s, mine_id: v }))} required /></Field>}
      {f.role === "corporate" && (
        <Field label="Subsidiary" hint="Leave empty for CIL headquarters (all subsidiaries)">
          <Select value={f.subsidiary_id} onChange={set("subsidiary_id")}>
            <option value="">Headquarters — all subsidiaries</option>
            {subs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
      )}
      {f.role === "contractor" && (
        <Field label="Contractor" required>
          <Select value={f.contractor_id} onChange={set("contractor_id")} required>
            <option value="">Select…</option>
            {contractors?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>Cancel</Button>
        <Button type="submit" loading={save.isPending}>{user ? "Save" : "Create user"}</Button>
      </div>
    </form>
  );
}

function UsersInner() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const [filters, setFilters] = useState({ status: params.get("status") ?? "", role: "", q: "" });
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState<{ user?: User } | null>(null);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["users", filters, page],
    queryFn: () => api<Page<User>>("/users", { query: { ...filters, page, size: 25 } }),
  });
  const approve = useMutation({
    mutationFn: (id: string) => api(`/users/${id}/approve`, { method: "POST" }),
    onSuccess: () => { toast.success("Access approved"); void qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div>
      <PageHeader title="Users & Access" subtitle="Who can sign in, and what each person can see and do" actions={<Button onClick={() => setModal({})}><Plus className="h-4 w-4" /> Add user</Button>} />
      <Card>
        <div className="filterbar grid grid-cols-1 gap-3 border-b border-line p-4 sm:grid-cols-3">
          <Input placeholder="Search name, username, email…" value={filters.q} onChange={(e) => { setFilters((f) => ({ ...f, q: e.target.value })); setPage(1); }} />
          <Select value={filters.role} onChange={(e) => { setFilters((f) => ({ ...f, role: e.target.value })); setPage(1); }} aria-label="Role">
            <option value="">All roles</option>{ROLES.map((r) => <option key={r} value={r}>{roleLabel[r]}</option>)}
          </Select>
          <Select value={filters.status} onChange={(e) => { setFilters((f) => ({ ...f, status: e.target.value })); setPage(1); }} aria-label="Status">
            <option value="">All statuses</option>{["pending", "active", "disabled"].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
          <EmptyState icon={<Users className="h-6 w-6" />} title="No users" />
        ) : (
          <>
            <Table>
              <thead><tr><Th>User</Th><Th>Role</Th><Th>Scope</Th><Th>Status</Th><Th>Last sign-in</Th><Th className="text-right">Actions</Th></tr></thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.id}>
                    <Td><span className="block font-medium">{u.full_name}</span><span className="text-xs text-muted">{u.username} · {u.email}</span>
                      {u.access_request_note && u.status === "pending" && <span className="mt-1 block text-xs italic text-muted">“{u.access_request_note}”</span>}</Td>
                    <Td>{roleLabel[u.role]}</Td>
                    <Td>{u.mine?.name ?? (u.subsidiary_id ? "Subsidiary" : u.role === "corporate" || u.role === "regulator" || u.role === "admin" ? "All" : "—")}</Td>
                    <Td><Badge tone={u.status === "active" ? "ok" : u.status === "pending" ? "warn" : "neutral"}>{humanize(u.status)}</Badge></Td>
                    <Td>{fmtDateTime(u.last_login_at)}</Td>
                    <Td className="text-right whitespace-nowrap">
                      {u.status === "pending" && <Button size="sm" onClick={() => approve.mutate(u.id)} loading={approve.isPending}><Check className="h-4 w-4" /> Approve</Button>}
                      <Button size="sm" variant="ghost" onClick={() => setModal({ user: u })}>Edit</Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} size={25} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.user ? `Edit ${modal.user.full_name}` : "Add user"} wide>
        {modal && <UserForm user={modal.user} onDone={() => setModal(null)} />}
      </Modal>
    </div>
  );
}

export default function UsersPage() {
  return (
    <Suspense fallback={<Loading />}>
      <UsersInner />
    </Suspense>
  );
}
