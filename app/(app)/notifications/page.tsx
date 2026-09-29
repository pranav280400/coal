"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Button, Card, cn, EmptyState, ErrorState, Loading, PageHeader, Pagination, Tabs } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fromNow } from "@/lib/format";
import type { Notification, Page } from "@/lib/types";

type View = "all" | "unread";

export default function NotificationsPage() {
  const qc = useQueryClient();
  const [view, setView] = useState<View>("all");
  const [page, setPage] = useState(1);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["notifications", view, page],
    queryFn: () => api<Page<Notification> & { unread: number }>("/notifications", { query: { unread_only: view === "unread", page, size: 25 } }),
  });
  const markRead = useMutation({
    mutationFn: (ids?: string[]) => api("/notifications/read", { body: { ids: ids ?? null } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="Alerts, reminders and escalations sent to you"
        actions={data?.unread ? <Button variant="outline" onClick={() => markRead.mutate(undefined)} loading={markRead.isPending}><CheckCheck className="h-4 w-4" /> Mark all read</Button> : null}
      />
      <div className="mb-4">
        <Tabs<View> value={view} onChange={(v) => { setView(v); setPage(1); }} tabs={[{ value: "all", label: "All" }, { value: "unread", label: "Unread", count: data?.unread }]} />
      </div>
      <Card>
        {isLoading ? <Loading /> : error ? <ErrorState message={errorMessage(error)} onRetry={() => refetch()} /> : !data?.items.length ? (
          <EmptyState icon={<Bell className="h-6 w-6" />} title="You're all caught up" />
        ) : (
          <>
            <ul className="divide-y divide-line">
              {data.items.map((n) => {
                const body = (
                  <div className={cn("flex gap-3 px-5 py-4", !n.read_at && "bg-copper-50/50")}>
                    <span className={cn("mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full", n.severity === "critical" ? "bg-bad" : n.severity === "warning" ? "bg-warn" : "bg-info")} />
                    <div className="min-w-0 flex-1">
                      <p className={cn("text-sm", !n.read_at ? "font-semibold" : "font-medium")}>{n.title}</p>
                      <p className="mt-0.5 text-sm text-muted">{n.body}</p>
                      <p className="mt-1 text-xs text-muted">{fromNow(n.created_at)} · {n.category}</p>
                    </div>
                  </div>
                );
                return (
                  <li key={n.id} onClick={() => !n.read_at && markRead.mutate([n.id])}>
                    {n.link ? <Link href={n.link} className="block hover:bg-fg/5">{body}</Link> : body}
                  </li>
                );
              })}
            </ul>
            <Pagination page={page} size={25} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
