"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Bell,
  ChevronDown,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  CircleHelp,
  ClipboardCheck,
  CloudUpload,
  CornerDownLeft,
  LayoutGrid,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings,
  Sparkles,
  TriangleAlert,
  WifiOff,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { toast } from "sonner";
import { Logo, MinistryMark } from "@/components/brand";
import { Shiny } from "@/components/fx";
import { ThemeToggle } from "@/components/theme-toggle";
import { LangToggle } from "@/components/lang-toggle";
import { SessionProvider, useSession } from "@/components/session";
import { isActive, NAV, NAV_GROUPS, NAV_MAIN, NAV_OTHER, QUICK_ACTIONS, type NavItem } from "@/components/shell/nav";
import { cn } from "@/components/ui";
import { api, buildUrl } from "@/lib/api";
import { roleLabel } from "@/lib/format";
import { useI18n, type Lang } from "@/lib/i18n";
import { onQueueChange, pendingCount, startAutoSync, syncNow } from "@/lib/offline";
import type { Me, SearchResults } from "@/lib/types";

const EASE = [0.22, 1, 0.36, 1] as const;

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

/** Job title under the user's name: their designation, else their role. */
function subtitleOf(me: Me, t: (s: string) => string): string {
  return me.designation || t(roleLabel[me.role] ?? me.role);
}

function useUnreadCount(): number {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api<{ unread: number }>("/notifications", { query: { size: 1 } }),
    refetchInterval: 120_000,
  });
  // Live updates over Server-Sent Events (Redis pub/sub → API → BFF proxy).
  useEffect(() => {
    const es = new EventSource(buildUrl("/notifications/stream"));
    es.addEventListener("notification", (ev) => {
      try {
        const n = JSON.parse((ev as MessageEvent).data) as { title: string; body: string; severity: string; link?: string };
        const show = n.severity === "critical" ? toast.error : n.severity === "warning" ? toast.warning : toast.info;
        show(n.title, { description: n.body.slice(0, 140) });
      } catch {
        /* ignore malformed frames */
      }
      void qc.invalidateQueries({ queryKey: ["notifications"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    });
    return () => es.close();
  }, [qc]);
  return data?.unread ?? 0;
}

function subscribeOnline(cb: () => void): () => void {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
}

function useQueueCount(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    startAutoSync();
    const refresh = () => void pendingCount().then(setCount).catch(() => undefined);
    refresh();
    return onQueueChange(refresh);
  }, []);
  return count;
}

async function signOut(clear: () => void) {
  await fetch("/api/auth/logout", { method: "POST" });
  clear();
  window.location.assign("/login");
}

function CountBadge({ count, className }: { count: number; className?: string }) {
  if (count <= 0) return null;
  return (
    <motion.span
      key={count}
      initial={{ scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 22 }}
      className={cn(
        "grid h-5 min-w-5 place-items-center rounded-full bg-copper-500 px-1 text-[11px] font-bold text-white shadow-[0_0_12px_rgb(212_136_78/0.7)]",
        className,
      )}
    >
      {count > 99 ? "99+" : count}
    </motion.span>
  );
}

function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" | "lg" }) {
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-full bg-gradient-to-br from-copper-400 to-copper-700 font-display font-bold text-white ring-2 ring-fg/10",
        size === "sm" ? "h-8 w-8 text-xs" : size === "lg" ? "h-12 w-12 text-[15px]" : "h-10 w-10 text-sm",
      )}
    >
      {initials(name)}
    </span>
  );
}

// ---------------------------------------------------------------- sidebar
function SideLink({ item, collapsed, unread }: { item: NavItem; collapsed: boolean; unread: number }) {
  const pathname = usePathname();
  const { can } = useSession();
  const { t } = useI18n();
  const active = isActive(pathname, item.href);
  const children = (item.children ?? []).filter((c) => !c.perm || can(c.perm));
  const hasChildren = children.length > 1 && !collapsed;
  const [open, setOpen] = useState(active);
  const Icon = item.icon;
  return (
    <div>
      <div className="relative flex items-center">
        <Link
          href={item.href}
          title={collapsed ? t(item.label) : undefined}
          onClick={() => hasChildren && setOpen(true)}
          className={cn(
            "group relative flex h-10 flex-1 items-center gap-3 rounded-xl px-3 text-[14px] font-medium transition-colors",
            active ? "text-ink" : "text-steel-600 hover:bg-fg/[0.04] hover:text-ink",
            collapsed && "justify-center px-0",
          )}
        >
          {active && (
            <motion.span
              layoutId="side-active"
              className="absolute inset-0 rounded-xl bg-gradient-to-r from-copper-500/25 via-copper-500/10 to-transparent ring-1 ring-copper-500/25"
              transition={{ type: "spring", stiffness: 460, damping: 38 }}
            >
              <span className="absolute top-1/2 -left-[13px] h-5 w-1 -translate-y-1/2 rounded-full bg-copper-400 shadow-[0_0_12px_#e3a473]" />
            </motion.span>
          )}
          <Icon
            className={cn("relative h-[18px] w-[18px] shrink-0 transition", active ? "text-copper-300" : "text-steel-500 group-hover:text-ink")}
            strokeWidth={1.9}
          />
          {!collapsed && <span className="relative flex-1 truncate">{t(item.label)}</span>}
          {item.badge === "notifications" && (
            <CountBadge count={unread} className={cn("relative", collapsed && "absolute top-0.5 right-1 h-4 min-w-4 text-[9px]")} />
          )}
        </Link>
        {hasChildren && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-label={t(item.label)}
            aria-expanded={open}
            className="absolute right-1 grid h-8 w-8 place-items-center rounded-lg text-steel-500 hover:text-ink"
          >
            <ChevronRight className={cn("h-4 w-4 transition", open && "rotate-90")} />
          </button>
        )}
      </div>
      <AnimatePresence initial={false}>
        {hasChildren && open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: EASE }}
            className="overflow-hidden"
          >
            <div className="mt-0.5 mb-1 ml-[21px] space-y-0.5 border-l border-fg/[0.08] pl-3.5">
              {children.map((c) => (
                <Link
                  key={c.href + c.label}
                  href={c.href}
                  className={cn("block rounded-lg px-3 py-1.5 text-[13px] transition", pathname === c.href ? "font-semibold text-copper-300" : "text-steel-500 hover:text-ink")}
                >
                  {t(c.label)}
                </Link>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Sidebar({ collapsed, onToggle, unread }: { collapsed: boolean; onToggle: () => void; unread: number }) {
  const { me, can } = useSession();
  const { t } = useI18n();
  const byHref = new Map(NAV_MAIN.map((n) => [n.href, n]));
  const groups = NAV_GROUPS.map((g) => ({
    label: g.label,
    items: g.hrefs.map((h) => byHref.get(h)).filter((n): n is NavItem => !!n && (!n.perm || can(n.perm))),
  })).filter((g) => g.items.length);
  const other = NAV_OTHER.filter((n) => !n.perm || can(n.perm));
  const scope = me.mine?.name ?? me.subsidiary_name;
  return (
    <aside
      className={cn(
        "glass sticky top-3 z-30 m-3 mr-0 hidden h-[calc(100dvh-24px)] shrink-0 flex-col rounded-[26px] transition-[width] duration-300 ease-out lg:flex",
        collapsed ? "w-[76px]" : "w-[260px]",
      )}
    >
      <div className={cn("flex h-[72px] shrink-0 items-center", collapsed ? "justify-center" : "justify-between pr-3 pl-5")}>
        <Link href="/dashboard" aria-label="Lumen">
          <Logo compact={collapsed} size="sm" />
        </Link>
        {!collapsed && (
          <button
            onClick={onToggle}
            className="grid h-8 w-8 place-items-center rounded-lg text-steel-500 transition hover:bg-fg/5 hover:text-ink"
            aria-label={t("Hide sidebar")}
            title={t("Hide sidebar")}
          >
            <ChevronsLeft className="h-4 w-4" />
          </button>
        )}
      </div>

      {!collapsed && scope && (
        <div className="mx-3 mb-2 flex items-center gap-2.5 rounded-xl border border-fg/[0.06] bg-fg/[0.03] px-3 py-2.5">
          <span className="h-2 w-2 shrink-0 rounded-full bg-ok shadow-[0_0_8px_#34c77b]" />
          <span className="min-w-0 leading-tight">
            <span className="block text-[10px] font-semibold tracking-[0.14em] text-steel-500 uppercase">{t("Workspace")}</span>
            <span className="block truncate text-[13px] font-semibold text-ink">{scope}</span>
          </span>
        </div>
      )}

      <nav className="scroll-thin flex-1 overflow-y-auto px-3 pb-2" aria-label={t("Main")}>
        {groups.map((g) => (
          <div key={g.label} className="mt-3 first:mt-1">
            {collapsed ? (
              <div className="mx-auto my-2 h-px w-6 bg-fg/10" />
            ) : (
              <p className="px-3 pb-1.5 text-[10px] font-semibold tracking-[0.16em] text-steel-400 uppercase">{t(g.label)}</p>
            )}
            <div className="space-y-0.5">
              {g.items.map((item) => (
                <SideLink key={item.href} item={item} collapsed={collapsed} unread={unread} />
              ))}
            </div>
          </div>
        ))}
        <div className="mt-3 border-t border-fg/[0.06] pt-3">
          <div className="space-y-0.5">
            {other.map((item) => (
              <SideLink key={item.href} item={item} collapsed={collapsed} unread={unread} />
            ))}
          </div>
        </div>
      </nav>

      {!collapsed && can("ai:use") && (
        <Link
          href="/assistant"
          className="group relative mx-3 mb-3 overflow-hidden rounded-2xl border border-copper-500/25 bg-gradient-to-br from-copper-500/20 via-copper-500/5 to-transparent p-3.5 transition hover:border-copper-500/45"
        >
          <span aria-hidden className="absolute -top-8 -right-8 h-20 w-20 rounded-full bg-copper-500/30 blur-2xl transition group-hover:bg-copper-500/45" />
          <span className="relative flex items-center gap-2 text-[13px] font-semibold text-ink">
            <Sparkles className="h-4 w-4 text-copper-300" /> <Shiny text={t("Ask Lumen AI")} />
          </span>
          <span className="relative mt-1 block text-xs leading-snug text-muted">{t("Answers grounded in the statute, with citations.")}</span>
        </Link>
      )}

      <div className={cn("flex shrink-0 items-center gap-2 border-t border-fg/[0.06] p-3", collapsed && "flex-col")}>
        <Link href="/settings" className={cn("flex min-w-0 flex-1 items-center gap-3 rounded-xl p-1.5 transition hover:bg-fg/[0.04]", collapsed && "justify-center")}>
          <Avatar name={me.full_name} size="sm" />
          {!collapsed && (
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-[13px] font-semibold text-ink">{me.full_name}</span>
              <span className="block truncate text-[11px] text-muted">{subtitleOf(me, t)}</span>
            </span>
          )}
        </Link>
        {collapsed && (
          <button
            onClick={onToggle}
            className="grid h-8 w-8 place-items-center rounded-lg text-steel-500 transition hover:bg-fg/5 hover:text-ink"
            aria-label={t("Show sidebar")}
            title={t("Show sidebar")}
          >
            <ChevronsRight className="h-4 w-4" />
          </button>
        )}
      </div>
    </aside>
  );
}

// -------------------------------------------------------- command palette
type Entry = { key: string; href: string; title: string; sub?: string; icon?: NavItem["icon"]; group: string };

function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const { can } = useSession();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [cursor, setCursor] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q.trim()), 220);
    return () => clearTimeout(timer);
  }, [q]);

  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api<SearchResults>("/search", { query: { q: debounced } }),
    enabled: open && debounced.length >= 2,
  });

  const entries = useMemo<Entry[]>(() => {
    const needle = q.trim().toLowerCase();
    const pages = NAV.filter((n) => (!n.perm || can(n.perm)) && (!needle || t(n.label).toLowerCase().includes(needle) || n.label.toLowerCase().includes(needle)))
      .slice(0, needle ? 6 : 8)
      .map((n) => ({ key: `nav:${n.href}`, href: n.href, title: t(n.label), icon: n.icon, group: t("Go to") }));
    const actions = QUICK_ACTIONS.filter((a) => can(a.perm) && (!needle || t(a.label).toLowerCase().includes(needle)))
      .slice(0, needle ? 3 : 5)
      .map((a) => ({ key: `act:${a.href}`, href: a.href, title: t(a.label), sub: t(a.hint), icon: a.icon, group: t("Create") }));
    const hits: Entry[] =
      data && debounced.length >= 2
        ? (Object.entries(data) as [keyof SearchResults, SearchResults[keyof SearchResults]][]).flatMap(([group, list]) =>
            list.map((h) => ({ key: `hit:${h.id}`, href: h.href, title: h.title, sub: h.subtitle, group: t(group.charAt(0).toUpperCase() + group.slice(1)) })),
          )
        : [];
    return [...hits, ...pages, ...actions];
  }, [q, debounced, data, can, t]);

  const go = (e: Entry | undefined) => {
    if (!e) return;
    onClose();
    router.push(e.href);
  };

  // keep the highlighted row in view
  useEffect(() => {
    listRef.current?.querySelector(`[data-idx="${cursor}"]`)?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  let lastGroup = "";
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex items-start justify-center bg-black/60 px-3 pt-[12vh] backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t("Global search")}
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.22, ease: EASE }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-[640px] overflow-hidden rounded-3xl border border-fg/10 bg-raised/95 shadow-[0_40px_120px_-20px_rgb(0_0_0/0.9),0_0_0_1px_rgb(212_136_78/0.08)]"
          >
            <div className="flex items-center gap-3 border-b border-fg/[0.07] px-5">
              <Search className="h-5 w-5 shrink-0 text-copper-400" />
              <input
                autoFocus
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setCursor(0);
                }}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setCursor((c) => Math.min(c + 1, entries.length - 1));
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setCursor((c) => Math.max(c - 1, 0));
                  } else if (e.key === "Enter") {
                    e.preventDefault();
                    go(entries[cursor]);
                  } else if (e.key === "Escape") {
                    onClose();
                  }
                }}
                placeholder={t("Search mines, inspections, contractors, regulations…")}
                aria-label={t("Global search")}
                className="h-16 w-full bg-transparent text-base text-ink outline-none placeholder:text-steel-500"
              />
              {isFetching && <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-copper-400 border-t-transparent" />}
              <kbd className="hidden shrink-0 rounded-md border border-fg/10 px-1.5 py-0.5 text-[11px] text-steel-500 sm:block">Esc</kbd>
            </div>
            <div ref={listRef} className="scroll-thin max-h-[52vh] overflow-y-auto p-2">
              {entries.length === 0 && (
                <p className="px-4 py-10 text-center text-sm text-muted">
                  {debounced.length >= 2 && !isFetching ? `${t("No matches")} — “${debounced}”` : t("Searching…")}
                </p>
              )}
              {entries.map((e, i) => {
                const header = e.group !== lastGroup ? e.group : null;
                lastGroup = e.group;
                const Icon = e.icon;
                return (
                  <div key={e.key}>
                    {header && <p className="px-3 pt-3 pb-1.5 text-[10px] font-semibold tracking-[0.16em] text-steel-500 uppercase">{header}</p>}
                    <button
                      data-idx={i}
                      onMouseMove={() => setCursor(i)}
                      onClick={() => go(e)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
                        i === cursor ? "bg-copper-500/12 text-ink ring-1 ring-copper-500/20" : "text-steel-600",
                      )}
                    >
                      <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg", i === cursor ? "bg-copper-500/20 text-copper-300" : "bg-fg/[0.04] text-steel-500")}>
                        {Icon ? <Icon className="h-4 w-4" /> : <Search className="h-4 w-4" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">{e.title}</span>
                        {e.sub && <span className="block truncate text-xs text-muted">{e.sub}</span>}
                      </span>
                      {i === cursor && <CornerDownLeft className="h-4 w-4 shrink-0 text-copper-400" />}
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="flex items-center gap-4 border-t border-fg/[0.07] px-5 py-2.5 text-[11px] text-steel-500">
              <span>↑↓ {t("to move")}</span>
              <span>↵ {t("to open")}</span>
              <span className="ml-auto">Ctrl K</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------- user menu
function UserMenu({ onLang }: { onLang: (l: Lang) => void }) {
  const { me } = useSession();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-2 rounded-full p-1 pr-2 transition hover:bg-fg/5" aria-haspopup="menu" aria-expanded={open}>
        <Avatar name={me.full_name} size="sm" />
        <ChevronDown className={cn("h-4 w-4 text-steel-500 transition", open && "rotate-180")} />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              role="menu"
              initial={{ opacity: 0, y: -6, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.97 }}
              transition={{ duration: 0.16, ease: EASE }}
              className="absolute right-0 z-50 mt-2 w-72 origin-top-right rounded-2xl border border-fg/10 bg-raised/95 p-2 shadow-[0_30px_60px_-20px_rgb(0_0_0/0.9)] backdrop-blur-xl"
            >
              <div className="flex items-center gap-3 border-b border-fg/[0.07] px-2.5 pt-1.5 pb-3">
                <Avatar name={me.full_name} />
                <div className="min-w-0">
                  <p className="truncate font-semibold text-ink">{me.full_name}</p>
                  <p className="truncate text-xs text-muted">
                    {t(roleLabel[me.role])}
                    {me.mine ? ` · ${me.mine.name}` : me.subsidiary_name ? ` · ${me.subsidiary_name}` : ""}
                  </p>
                </div>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-fg/[0.07] px-2.5 py-3 text-sm text-ink">
                <span>{t("Language")}</span>
                <LangToggle size="sm" onChange={onLang} />
              </div>
              <Link href="/settings" onClick={() => setOpen(false)} className="mt-1 flex items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-sm text-steel-600 transition hover:bg-fg/5 hover:text-ink">
                <Settings className="h-4 w-4" /> {t("Settings")}
              </Link>
              <Link href="/help" onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-sm text-steel-600 transition hover:bg-fg/5 hover:text-ink">
                <CircleHelp className="h-4 w-4" /> {t("Help")}
              </Link>
              <button onClick={() => void signOut(() => qc.clear())} className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-sm text-bad transition hover:bg-bad-soft">
                <LogOut className="h-4 w-4" /> {t("Sign out")}
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function StatusPills({ online, queued }: { online: boolean; queued: number }) {
  const { t } = useI18n();
  return (
    <>
      {!online && (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-warn-soft px-3 py-1.5 text-xs font-semibold text-warn ring-1 ring-warn/20">
          <WifiOff className="h-3.5 w-3.5" /> {t("Offline")}
        </span>
      )}
      {queued > 0 && (
        <button
          onClick={() => void syncNow()}
          className="inline-flex items-center gap-1.5 rounded-full bg-info-soft px-3 py-1.5 text-xs font-semibold text-info ring-1 ring-info/20"
          title={t("Field reports waiting to sync")}
        >
          <CloudUpload className="h-3.5 w-3.5" /> {queued} {t("to sync")}
        </button>
      )}
    </>
  );
}

/** "Section / Page" trail for the top bar, from the nav model. */
function useTrail(): { section: string | null; page: string } {
  const pathname = usePathname();
  const item = NAV.find((n) => isActive(pathname, n.href));
  const group = item ? NAV_GROUPS.find((g) => g.hrefs.includes(item.href)) : undefined;
  return { section: group?.label ?? (item && NAV_OTHER.includes(item) ? "Account" : null), page: item?.label ?? "Lumen" };
}

// ------------------------------------------------------------ mobile shell
/** Bottom sheet used by the mobile "+" and "Menu" tabs. */
function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const { t } = useI18n();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end bg-black/60 backdrop-blur-sm lg:hidden"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t(title)}
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            className="flex max-h-[88dvh] w-full flex-col rounded-t-[28px] border-t border-fg/10 bg-raised pb-[env(safe-area-inset-bottom)] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 justify-center pt-2.5">
              <span className="h-1.5 w-10 rounded-full bg-fg/15" aria-hidden />
            </div>
            <div className="flex shrink-0 items-center justify-between px-5 pt-3 pb-2">
              <h2 className="text-lg font-bold text-ink">{t(title)}</h2>
              <button onClick={onClose} className="grid h-11 w-11 place-items-center rounded-full text-ink active:bg-fg/5" aria-label={t("Close")}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="scroll-thin overflow-y-auto px-3 pb-4">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function SheetRow({ href, icon: Icon, label, hint, onClick, badge, active }: {
  href: string; icon: NavItem["icon"]; label: string; hint?: string; onClick: () => void; badge?: number; active?: boolean;
}) {
  const { t } = useI18n();
  return (
    <Link href={href} onClick={onClick} className={cn("flex min-h-14 items-center gap-4 rounded-2xl px-3 py-2.5 active:bg-fg/5", active && "bg-copper-500/10")}>
      <span className={cn("grid h-11 w-11 shrink-0 place-items-center rounded-xl", active ? "bg-copper-600 text-white" : "bg-fg/[0.05] text-copper-300")}>
        <Icon className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-medium text-ink">{t(label)}</span>
        {hint && <span className="block text-[13px] text-muted">{t(hint)}</span>}
      </span>
      {badge ? <CountBadge count={badge} /> : <ChevronRight className="h-5 w-5 text-steel-400" />}
    </Link>
  );
}

function MobileTabBar({ unread, onLang }: { unread: number; onLang: (l: Lang) => void }) {
  const pathname = usePathname();
  const { me, can } = useSession();
  const { t } = useI18n();
  const qc = useQueryClient();
  const [sheet, setSheet] = useState<"create" | "menu" | null>(null);
  const close = () => setSheet(null);
  const actions = QUICK_ACTIONS.filter((a) => can(a.perm));
  const tabs = [
    { href: "/dashboard", label: "Home", icon: LayoutGrid },
    { href: "/inspections", label: "Inspections", icon: ClipboardCheck },
    null, // centre "+" button
    { href: "/violations", label: "Violations", icon: TriangleAlert },
  ];
  return (
    <>
      <nav className="fixed inset-x-3 bottom-[calc(10px+env(safe-area-inset-bottom))] z-40 lg:hidden" aria-label={t("Main")}>
        <div className="glass mx-auto grid h-16 max-w-md grid-cols-5 rounded-[22px] shadow-[0_20px_50px_-10px_rgb(0_0_0/0.9)]">
          {tabs.map((tab) => {
            if (!tab) {
              return (
                <div key="create" className="flex items-center justify-center">
                  <button
                    onClick={() => setSheet("create")}
                    disabled={!actions.length}
                    className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-b from-copper-500 to-copper-600 text-white shadow-[0_10px_24px_-8px_rgb(212_136_78/0.9)] transition active:scale-95 disabled:opacity-40"
                    aria-label={t("Create new")}
                  >
                    <Plus className="h-6 w-6" />
                  </button>
                </div>
              );
            }
            const active = isActive(pathname, tab.href);
            const Icon = tab.icon;
            return (
              <Link key={tab.href} href={tab.href} className="relative flex flex-col items-center justify-center gap-1 text-[10px] font-semibold">
                {active && <motion.span layoutId="tab-active" className="absolute inset-1.5 rounded-2xl bg-fg/[0.06]" transition={{ type: "spring", stiffness: 480, damping: 38 }} />}
                <Icon className={cn("relative h-5 w-5", active ? "text-copper-300" : "text-steel-500")} strokeWidth={active ? 2.2 : 1.8} />
                <span className={cn("relative", active ? "text-ink" : "text-steel-500")}>{t(tab.label)}</span>
              </Link>
            );
          })}
          <button onClick={() => setSheet("menu")} className="relative flex flex-col items-center justify-center gap-1 text-[10px] font-semibold text-steel-500">
            <Menu className="h-5 w-5" strokeWidth={1.8} />
            {t("Menu")}
            {unread > 0 && <span className="absolute top-3 right-[30%] h-2 w-2 rounded-full bg-copper-400 shadow-[0_0_8px_#e3a473]" />}
          </button>
        </div>
      </nav>

      <Sheet open={sheet === "create"} onClose={close} title="Create new">
        {actions.map((a) => (
          <SheetRow key={a.href} href={a.href} icon={a.icon} label={a.label} hint={a.hint} onClick={close} />
        ))}
      </Sheet>

      <Sheet open={sheet === "menu"} onClose={close} title="Menu">
        <div className="mb-2 flex items-center gap-3 rounded-2xl border border-fg/[0.06] bg-fg/[0.03] px-3 py-3">
          <Avatar name={me.full_name} size="lg" />
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block truncate font-semibold text-ink">{me.full_name}</span>
            <span className="block truncate text-[13px] text-muted">{subtitleOf(me, t)}</span>
          </span>
          <LangToggle size="sm" onChange={onLang} />
        </div>
        {NAV_GROUPS.map((g) => {
          const items = NAV_MAIN.filter((n) => g.hrefs.includes(n.href) && (!n.perm || can(n.perm)));
          if (!items.length) return null;
          return (
            <div key={g.label}>
              <p className="px-3 pt-4 pb-1 text-[11px] font-semibold tracking-[0.14em] text-steel-500 uppercase">{t(g.label)}</p>
              {items.map((n) => (
                <SheetRow key={n.href} href={n.href} icon={n.icon} label={n.label} onClick={close}
                  badge={n.badge === "notifications" ? unread : undefined} active={isActive(pathname, n.href)} />
              ))}
            </div>
          );
        })}
        <p className="px-3 pt-4 pb-1 text-[11px] font-semibold tracking-[0.14em] text-steel-500 uppercase">{t("Other")}</p>
        {NAV_OTHER.filter((n) => !n.perm || can(n.perm)).map((n) => (
          <SheetRow key={n.href} href={n.href} icon={n.icon} label={n.label} onClick={close} active={isActive(pathname, n.href)} />
        ))}
        <button
          onClick={() => void signOut(() => qc.clear())}
          className="mt-3 flex min-h-14 w-full items-center gap-4 rounded-2xl px-3 text-[15px] font-medium text-bad active:bg-bad-soft"
        >
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-bad-soft"><LogOut className="h-5 w-5" /></span>
          {t("Sign out")}
        </button>
      </Sheet>
    </>
  );
}

// ------------------------------------------------------------------ shell
function Shell({ children }: { children: ReactNode }) {
  const { me } = useSession();
  const { t, chosen, setLang } = useI18n();
  const qc = useQueryClient();
  const reduce = useReducedMotion();
  const trail = useTrail();
  // First visit on this device: follow the language saved on the user's profile.
  useEffect(() => {
    if (!chosen && me.preferred_language === "hi") setLang("hi", { persist: false });
  }, [chosen, me.preferred_language, setLang]);
  const saveLang = (lang: Lang) => {
    if (me.preferred_language === lang) return;
    void api("/auth/me", { method: "PATCH", body: { preferred_language: lang } })
      .then(() => qc.invalidateQueries({ queryKey: ["me"] }))
      .catch(() => undefined);
  };
  // The shell only renders client-side after the session loads, so reading storage here is hydration-safe.
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("cmg-sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  const unread = useUnreadCount();
  const online = useOnline();
  const queued = useQueueCount();
  const toggle = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem("cmg-sidebar", c ? "open" : "collapsed");
      } catch {
        /* ignore */
      }
      return !c;
    });
  };
  const [palette, setPalette] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="app-backdrop flex min-h-dvh">
      <Sidebar collapsed={collapsed} onToggle={toggle} unread={unread} />
      <div className="flex min-w-0 flex-1 flex-col">
        {/* desktop top bar */}
        <header className="glass sticky top-3 z-20 mx-3 mt-3 hidden h-16 items-center gap-4 rounded-[20px] pr-2.5 pl-6 lg:flex">
          <div className="min-w-0">
            {trail.section && <p className="text-[10px] font-semibold tracking-[0.16em] text-steel-500 uppercase">{t(trail.section)}</p>}
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={trail.page}
                initial={reduce ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18 }}
                className="truncate font-display text-[15px] font-bold text-ink"
              >
                {t(trail.page)}
              </motion.p>
            </AnimatePresence>
          </div>
          <button
            onClick={() => setPalette(true)}
            className="group mx-auto flex h-10 w-full max-w-[460px] items-center gap-3 rounded-xl border border-fg/[0.07] bg-fg/[0.03] px-3.5 text-sm text-steel-500 transition hover:border-copper-500/30 hover:bg-fg/[0.05]"
            aria-label={t("Global search")}
          >
            <Search className="h-4 w-4 transition group-hover:text-copper-400" />
            <span className="flex-1 truncate text-left">{t("Search mines, inspections, contractors, regulations…")}</span>
            <kbd className="rounded-md border border-fg/10 bg-fg/[0.04] px-1.5 py-0.5 font-sans text-[11px]">Ctrl K</kbd>
          </button>
          <div className="flex items-center gap-2">
            <StatusPills online={online} queued={queued} />
            <ThemeToggle className="ring-0" />
            <Link href="/notifications" className="relative grid h-10 w-10 place-items-center rounded-xl text-steel-600 transition hover:bg-fg/5 hover:text-ink" aria-label={`${t("Notifications")} (${unread})`}>
              <Bell className="h-[19px] w-[19px]" strokeWidth={1.9} />
              <CountBadge count={unread} className="absolute -top-0.5 -right-0.5 h-[18px] min-w-[18px] text-[10px] ring-2 ring-surface" />
            </Link>
            <MinistryMark className="hidden border-x border-fg/[0.07] px-4 xl:flex [&_img]:h-8" />
            <UserMenu onLang={saveLang} />
          </div>
        </header>

        {/* mobile app bar */}
        <header className="glass sticky top-0 z-30 border-x-0 border-t-0 pt-[env(safe-area-inset-top)] lg:hidden">
          <div className="flex h-14 items-center gap-1 px-4">
            <Link href="/dashboard" className="mr-auto" aria-label="Lumen">
              <Logo size="sm" />
            </Link>
            <ThemeToggle className="h-11 w-11 ring-0" />
            <button onClick={() => setPalette(true)} className="grid h-11 w-11 place-items-center rounded-full text-ink active:bg-fg/5" aria-label={t("Search")}>
              <Search className="h-5 w-5" />
            </button>
            <Link href="/notifications" className="relative grid h-11 w-11 place-items-center rounded-full text-ink active:bg-fg/5" aria-label={t("Notifications")}>
              <Bell className="h-5 w-5" />
              <CountBadge count={unread} className="absolute top-1.5 right-1 h-4 min-w-4 text-[9px] ring-2 ring-surface" />
            </Link>
          </div>
        </header>
        {(!online || queued > 0) && (
          <div className="flex gap-2 px-4 pt-3 lg:hidden">
            <StatusPills online={online} queued={queued} />
          </div>
        )}
        <main className="w-full max-w-[1600px] flex-1 px-4 pt-5 pb-[calc(110px+env(safe-area-inset-bottom))] sm:px-6 lg:mx-auto lg:px-8 lg:pt-7 lg:pb-12">
          {children}
        </main>
        <footer className="hidden items-center justify-between px-8 pb-6 text-[11px] text-steel-400 lg:flex">
          <span>Lumen · {t("Ministry of Coal · Government of India")}</span>
          <Link href="/help" className="inline-flex items-center gap-1 transition hover:text-ink">
            {t("Help")} <ArrowRight className="h-3 w-3" />
          </Link>
        </footer>
      </div>
      <MobileTabBar unread={unread} onLang={saveLang} />
      <CommandPalette key={palette ? "open" : "closed"} open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <Shell>{children}</Shell>
    </SessionProvider>
  );
}
