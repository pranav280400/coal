"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  FileSearch,
  FileText,
  History,
  LoaderCircle,
  Mic,
  MicOff,
  Paperclip,
  RotateCcw,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  Square,
  Trash,
  TriangleAlert,
  User,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState, useSyncExternalStore, type DragEvent } from "react";
import { motion, useReducedMotion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { Shiny, Split } from "@/components/fx";
import { Stagger, StaggerItem, useSpotlight } from "@/components/motion";
import { useSession } from "@/components/session";
import { Badge, Button, cn, EmptyState, Input, Loading, Modal } from "@/components/ui";
import { api, errorMessage, sse } from "@/lib/api";
import { fromNow, humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ChatMessage, ChatSession, Citation, SimilarItem } from "@/lib/types";

// ------------------------------------------------------------------ content
const LANGS = [
  { value: "auto", label: "Auto-detect" },
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
  { value: "bn", label: "বাংলা" },
  { value: "or", label: "ଓଡ଼ିଆ" },
  { value: "te", label: "తెలుగు" },
  { value: "mr", label: "मराठी" },
  { value: "ta", label: "தமிழ்" },
];

const QUICK: { icon: LucideIcon; tone: string; title: string; hint: string }[] = [
  { icon: ShieldAlert, tone: "bg-copper-500/12 text-copper-300", title: "How do I raise a grievance?", hint: "Get step-by-step guidance on filing a grievance." },
  { icon: FileText, tone: "bg-ok-soft text-ok", title: "Which statutory items are due soon?", hint: "Check upcoming compliance deadlines and inspections." },
  { icon: TriangleAlert, tone: "bg-bad-soft text-bad", title: "What is the PM10 limit and what should I do if it is exceeded?", hint: "Understand thresholds and action steps." },
  { icon: BookOpen, tone: "bg-violet-soft text-violet", title: "What are the rules for haul road safety in opencast mines?", hint: "View key safety regulations and guidelines." },
  { icon: CalendarDays, tone: "bg-info-soft text-info", title: "How long do I have to fix a critical violation?", hint: "Know the timeline and next steps." },
  { icon: FileSearch, tone: "bg-[rgb(45_212_191/0.12)] text-[#5eead4]", title: "Summarise this month's inspection findings for my mines.", hint: "Get a quick summary of key points." },
];

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.txt,.csv,.md,application/pdf,image/png,image/jpeg,image/webp,image/tiff,text/plain,text/csv";
const MAX_FILES = 3;

type Stage = "thinking" | "searching" | "writing";
const STAGE_LABEL: Record<Stage, string> = {
  thinking: "Understanding your question…",
  searching: "Searching rules and your records…",
  writing: "Writing the answer…",
};

interface Turn {
  role: "user" | "assistant";
  content: string;
  files?: string[];
  citations?: Citation[];
  suggestions?: string[];
  stage?: Stage | null;
  error?: string | null;
  question?: string;
  startedAt?: number;
}

interface Attachment {
  key: string;
  name: string;
  status: "uploading" | "ready" | "error";
  id?: string;
  pages?: number;
  error?: string;
}

// -------------------------------------------------------------- artwork
/** Friendly robot mascot for the greeting banner. */
function RobotAvatar() {
  return (
    <svg viewBox="0 0 120 120" className="h-full w-full" aria-hidden>
      <circle cx="60" cy="60" r="58" fill="#1f1711" stroke="#d4884e" strokeOpacity=".35" strokeWidth="1.5" />
      <path d="M92 20l2.2 5.6L100 28l-5.8 2.4L92 36l-2.2-5.6L84 28l5.8-2.4z" fill="#D89A68" />
      <line x1="60" y1="30" x2="60" y2="20" stroke="#5f3218" strokeWidth="3" strokeLinecap="round" />
      <circle cx="60" cy="17" r="4.5" fill="#B86B35" />
      <rect x="22" y="52" width="10" height="22" rx="5" fill="#9a5629" />
      <rect x="88" y="52" width="10" height="22" rx="5" fill="#9a5629" />
      <rect x="28" y="30" width="64" height="62" rx="20" fill="#D89A68" />
      <rect x="28" y="30" width="64" height="62" rx="20" fill="url(#rb-shade)" />
      <rect x="36" y="42" width="48" height="36" rx="13" fill="#3a2418" />
      <ellipse cx="50" cy="57" rx="4.2" ry="5.2" fill="#FFE4C8" />
      <ellipse cx="70" cy="57" rx="4.2" ry="5.2" fill="#FFE4C8" />
      <path d="M52 67q8 6 16 0" stroke="#FFE4C8" strokeWidth="3" fill="none" strokeLinecap="round" />
      <circle cx="43" cy="66" r="2.5" fill="#E08A64" opacity=".7" />
      <circle cx="77" cy="66" r="2.5" fill="#E08A64" opacity=".7" />
      <defs>
        <linearGradient id="rb-shade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity=".28" />
          <stop offset="1" stopColor="#7e4520" stopOpacity=".25" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/** Faint line drawing of a pit-head headframe on rolling hills (banner decoration). */
function HeadframeArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 360 140" className={className} fill="none" aria-hidden>
      <path d="M0 128c40-18 70-22 110-14s70 6 110-10 80-14 140 4" stroke="currentColor" strokeWidth="1.5" opacity=".7" />
      <path d="M0 110c50-14 90-30 140-24s60 16 110 2 70-26 110-18" stroke="currentColor" strokeWidth="1.2" opacity=".45" />
      <g stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
        <path d="M232 124L250 30M284 124L266 30M250 30h16" />
        <path d="M238 96h40M242 74h32M246 52h24" opacity=".8" />
        <path d="M238 96l36-22M242 74l28-22M278 96l-36-22M274 74l-28-22" opacity=".55" />
        <circle cx="258" cy="24" r="10" />
        <circle cx="258" cy="24" r="2" />
        <path d="M258 14v20M248 24h20" opacity=".6" />
        <path d="M268 30l40 64M300 124v-30h20v30" />
        <path d="M200 124v-22h26v22" opacity=".7" />
      </g>
    </svg>
  );
}

function Hero({ name }: { name: string }) {
  const { t } = useI18n();
  return (
    <section className="relative isolate overflow-hidden rounded-[28px] border border-fg/[0.07] bg-surface px-5 py-5 sm:px-7 sm:py-6">
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(600px_260px_at_90%_-30%,rgb(212_136_78/0.3),transparent_70%),radial-gradient(400px_200px_at_5%_120%,rgb(212_136_78/0.12),transparent_70%)]" />
      <HeadframeArt className="pointer-events-none absolute right-0 bottom-0 hidden h-[118%] text-copper-400/25 md:block" />
      <div className="relative flex items-center gap-5">
        <span className="h-[84px] w-[84px] shrink-0 drop-shadow-[0_0_30px_rgb(212_136_78/0.35)] motion-safe:animate-float sm:h-[104px] sm:w-[104px]">
          <RobotAvatar />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium"><Shiny text={t("AI Assistant")} /></p>
          <h1 className="mt-0.5 font-display text-[24px] leading-tight font-bold tracking-[-0.03em] text-ink sm:text-[32px]">
            <Split text={t("Hello, {name}!", { name })} by="chars" delay={18} /> <span aria-hidden>👋</span>
          </h1>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-steel-600 sm:text-[15px]">
            {t("I'm your AI assistant for Lumen. I can help you with rules, inspections, deadlines, mine records, or answer any questions related to coal mining and compliance.")}
          </p>
        </div>
        <div className="relative mr-36 hidden shrink-0 -rotate-6 lg:block" aria-hidden>
          <span className="font-hand text-[30px] text-copper-400">{t("Ask me anything...")}</span>
          <svg viewBox="0 0 60 26" className="absolute -bottom-6 left-10 h-6 w-14 text-copper-400" fill="none">
            <path d="M2 4c10 14 26 18 50 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <path d="M45 10l8 6-9 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------ building blocks
function sourceHref(c: Citation): string | null {
  if (c.source_type === "violation") return `/violations/${c.source_id}`;
  if (c.source_type === "inspection") return `/inspections/${c.source_id}`;
  if (c.source_type === "document") return `/documents/${c.source_id}`;
  return null;
}

function Citations({ items }: { items: Citation[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {items.map((c) => {
        const href = sourceHref(c);
        const chip = (
          <span className="inline-flex max-w-72 items-center gap-1 truncate rounded-lg bg-copper-50 px-2 py-1 text-xs text-copper-400" title={c.snippet}>
            {c.source_type === "attachment" ? <Paperclip className="h-3 w-3 shrink-0" /> : <strong>[{c.index}]</strong>} {c.title}
          </span>
        );
        return href ? <Link key={c.index} href={href}>{chip}</Link> : <span key={c.index}>{chip}</span>;
      })}
    </div>
  );
}

function Progress({ stage, startedAt, reading }: { stage: Stage; startedAt: number; reading: boolean }) {
  const { t } = useI18n();
  const [now, setNow] = useState(startedAt);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const secs = Math.max(0, Math.round((now - startedAt) / 1000));
  return (
    <div className="flex flex-col gap-1.5 py-0.5" role="status" aria-live="polite">
      <span className="flex items-center gap-2.5 text-sm text-muted">
        <span className="flex gap-1" aria-hidden>
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-copper-500" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-copper-500 [animation-delay:120ms]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-copper-500 [animation-delay:240ms]" />
        </span>
        {t(reading && stage === "searching" ? "Reading your file…" : STAGE_LABEL[stage])}
      </span>
      {secs >= 12 && <span className="text-xs text-steel-500">{t("Still working — detailed answers can take up to a minute on this server.")}</span>}
    </div>
  );
}

// Minimal typing for the browser speech API (not in the TS DOM lib everywhere).
interface SpeechResultEvent { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }
interface Recognizer {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}
type RecognizerCtor = new () => Recognizer;
function speechCtor(): RecognizerCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognizerCtor; webkitSpeechRecognition?: RecognizerCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noopSubscribe = () => () => undefined;

function SimilarRecords({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const search = useMutation({
    mutationFn: () => api<SimilarItem[]>("/ai/search", { body: { query: q, source_types: null, limit: 15 } }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Modal open={open} onClose={onClose} title="Find similar records" wide>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 2) search.mutate(); }} className="flex gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Describe what you're looking for, e.g. 'dust suppression failures near haul roads'")} />
        <Button type="submit" loading={search.isPending}><Search className="h-4 w-4" /> Search</Button>
      </form>
      <div className="mt-4">
        {search.isPending ? <Loading label="Searching…" /> : search.data ? (
          search.data.length ? (
            <ul className="space-y-2">
              {search.data.map((h) => {
                const href = sourceHref({ index: 0, source_type: h.source_type, source_id: h.source_id, title: h.title, score: h.score, snippet: h.snippet });
                const inner = (
                  <div className="rounded-xl border border-line p-3 hover:bg-fg/5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{h.title}</span>
                      <span className="flex gap-1.5"><Badge tone="neutral">{humanize(h.source_type)}</Badge><Badge tone="info">{Math.round(h.score * 100)}%</Badge></span>
                    </div>
                    <p className="mt-1 line-clamp-3 text-sm text-muted">{h.snippet}</p>
                  </div>
                );
                return <li key={`${h.source_type}-${h.source_id}-${h.snippet.slice(0, 10)}`}>{href ? <Link href={href} onClick={onClose}>{inner}</Link> : inner}</li>;
              })}
            </ul>
          ) : <EmptyState title="No matches" body="Try different wording — search works on meaning, not keywords." />
        ) : <p className="text-sm text-muted">{t("Search regulations, inspection reports, violations and uploaded documents by meaning, not just exact words.")}</p>}
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ page
/** A quick-question card: a faint copper spotlight follows the pointer as a click cue. */
function QuickCard({ icon: Icon, tone, title, hint, onAsk }: (typeof QUICK)[number] & { onAsk: (q: string) => void }) {
  const { t } = useI18n();
  const { handlers, layer } = useSpotlight();
  return (
    <button
      type="button"
      onClick={() => onAsk(t(title))}
      {...handlers}
      className="group relative flex h-full w-full items-center gap-4 overflow-hidden rounded-2xl border border-fg/[0.07] bg-raised/60 p-4 text-left transition duration-300 hover:-translate-y-0.5 hover:border-copper-500/35 hover:bg-raised hover:shadow-lift sm:p-5"
    >
      {layer}
      <span className={cn("relative grid h-11 w-11 shrink-0 place-items-center rounded-xl", tone)}><Icon className="h-5 w-5" /></span>
      <span className="relative min-w-0 flex-1">
        <span className="block text-[15px] leading-snug font-semibold text-ink">{t(title)}</span>
        <span className="mt-1.5 block text-[13px] leading-snug text-muted">{t(hint)}</span>
      </span>
      <ChevronRight className="relative h-5 w-5 shrink-0 text-steel-400 transition group-hover:translate-x-0.5 group-hover:text-copper-600" />
    </button>
  );
}

function Assistant() {
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const { me } = useSession();
  const { lang: uiLang, t } = useI18n();
  const reduce = useReducedMotion();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [lang, setLang] = useState(uiLang === "hi" ? "hi" : "auto");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<Attachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const [listening, setListening] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const recRef = useRef<Recognizer | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const initial = useRef(params.get("q"));
  // Known only in the browser: render without the mic on the server, then add it if supported.
  const canSpeak = useSyncExternalStore(noopSubscribe, () => speechCtor() !== null, () => false);

  const { data: status } = useQuery({
    queryKey: ["ai-status"],
    queryFn: () => api<{ ready: boolean }>("/ai/status"),
    refetchInterval: 60_000,
  });
  const { data: sessions = [] } = useQuery({ queryKey: ["chat-sessions"], queryFn: () => api<ChatSession[]>("/ai/sessions") });
  const del = useMutation({
    mutationFn: (id: string) => api(`/ai/sessions/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) => {
      void qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      if (id === sessionId) { setSessionId(null); setTurns([]); }
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const patchLast = (fn: (x: Turn) => Turn) => setTurns((all) => all.map((x, i) => (i === all.length - 1 ? fn(x) : x)));

  const newChat = () => {
    abortRef.current?.abort();
    setSessionId(null);
    setTurns([]);
    setFiles([]);
    setHistoryOpen(false);
    boxRef.current?.focus();
  };

  const load = async (id: string) => {
    abortRef.current?.abort();
    setHistoryOpen(false);
    setSessionId(id);
    setFiles([]);
    const history = await api<ChatMessage[]>(`/ai/sessions/${id}/messages`);
    setTurns(history.map((m) => ({ role: m.role, content: m.content, citations: m.citations ?? [] })));
  };

  // ---- attachments
  const upload = async (list: FileList | File[]) => {
    const picked = Array.from(list).slice(0, Math.max(0, MAX_FILES - files.length));
    if (list.length > picked.length) toast.info(t("You can attach up to 3 files."));
    for (const f of picked) {
      const key = `${f.name}-${f.size}-${Date.now()}`;
      setFiles((all) => [...all, { key, name: f.name, status: "uploading" }]);
      const form = new FormData();
      form.append("file", f, f.name);
      try {
        const res = await api<{ id: string; pages: number; filename: string }>("/ai/attachments", { method: "POST", form });
        setFiles((all) => all.map((x) => (x.key === key ? { ...x, status: "ready", id: res.id, pages: res.pages, name: res.filename } : x)));
      } catch (e) {
        setFiles((all) => all.map((x) => (x.key === key ? { ...x, status: "error", error: errorMessage(e) } : x)));
      }
    }
    boxRef.current?.focus();
  };
  const readyIds = files.filter((f) => f.status === "ready" && f.id).map((f) => f.id!);
  const uploading = files.some((f) => f.status === "uploading");

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) void upload(e.dataTransfer.files);
  };

  // ---- voice input
  const toggleMic = () => {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const Ctor = speechCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = lang === "hi" || (lang === "auto" && uiLang === "hi") ? "hi-IN" : "en-IN";
    rec.interimResults = true;
    rec.continuous = false;
    const base = input ? `${input.trim()} ` : "";
    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      setInput(base + text);
    };
    rec.onend = () => { setListening(false); boxRef.current?.focus(); };
    rec.onerror = () => { setListening(false); toast.error(t("Voice input is not available right now.")); };
    recRef.current = rec;
    setListening(true);
    rec.start();
  };

  // ---- send
  const send = useCallback(
    async (text: string) => {
      const ids = files.filter((f) => f.status === "ready" && f.id).map((f) => f.id!);
      const names = files.filter((f) => f.status === "ready").map((f) => f.name);
      const q = text.trim() || (ids.length ? t("Summarise the attached file.") : "");
      if (!q || busy || files.some((f) => f.status === "uploading")) return;
      recRef.current?.stop();
      setInput("");
      if (boxRef.current) boxRef.current.style.height = "auto";
      setBusy(true);
      setTurns((all) => [
        ...all.map((x) => ({ ...x, suggestions: undefined })),
        { role: "user", content: q, files: names },
        { role: "assistant", content: "", citations: [], stage: "thinking", question: q, startedAt: Date.now() },
      ]);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let finished = false;
      try {
        for await (const ev of sse("/ai/chat", { message: q, session_id: sessionId, language: lang, attachment_ids: ids }, ctrl.signal)) {
          const data = ev.data as Record<string, unknown>;
          if (ev.event === "meta") setSessionId(data.session_id as string);
          else if (ev.event === "status") patchLast((x) => (x.content ? x : { ...x, stage: data.stage as Stage }));
          else if (ev.event === "citations") patchLast((x) => ({ ...x, citations: data.citations as Citation[] }));
          else if (ev.event === "token") patchLast((x) => ({ ...x, stage: null, content: x.content + (data.t as string) }));
          else if (ev.event === "suggestions") patchLast((x) => ({ ...x, suggestions: data.items as string[] }));
          else if (ev.event === "error") patchLast((x) => ({ ...x, stage: null, error: data.detail as string }));
          else if (ev.event === "done") finished = true;
        }
        if (!finished && !ctrl.signal.aborted) {
          patchLast((x) => (x.error ? x : { ...x, stage: null, error: "The connection closed before the answer finished." }));
        }
        void qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      } catch (e) {
        if (!ctrl.signal.aborted) patchLast((x) => ({ ...x, stage: null, error: errorMessage(e) }));
      } finally {
        patchLast((x) => ({ ...x, stage: null }));
        setBusy(false);
        abortRef.current = null;
        boxRef.current?.focus();
      }
    },
    [busy, files, lang, qc, sessionId, t],
  );

  const stop = () => {
    abortRef.current?.abort();
    patchLast((x) => ({ ...x, stage: null, content: x.content || t("Stopped.") }));
  };

  useEffect(() => {
    if (initial.current) {
      const q = initial.current;
      initial.current = null;
      router.replace("/assistant");
      void send(q);
    }
  }, [router, send]);

  const last = turns[turns.length - 1];
  const statusDot = uploading
    ? { cls: "bg-warn", label: "Reading your file…" }
    : busy
      ? { cls: "bg-warn", label: "Answering…" }
      : status && !status.ready
        ? { cls: "bg-bad", label: "AI assistant is offline" }
        : { cls: "bg-ok", label: "AI assistant is ready" };

  return (
    <div className="space-y-5">
      <Hero name={me.full_name} />

      <section
        className={cn(
          "relative rounded-[28px] border border-fg/[0.07] bg-surface/80 p-4 shadow-card backdrop-blur sm:p-6",
          dragging && "ring-2 ring-copper-400 ring-offset-2 ring-offset-canvas",
        )}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
        onDrop={onDrop}
      >
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center rounded-2xl bg-copper-50/90 text-copper-400">
            <span className="flex items-center gap-2 text-base font-semibold"><Paperclip className="h-5 w-5" /> {t("Drop a PDF, image or text file to attach it")}</span>
          </div>
        )}

        {!turns.length ? (
          <>
            <h2 className="text-lg font-bold text-ink sm:text-xl">{t("Quick Questions")}</h2>
            <p className="mt-1 text-sm text-muted">{t("Choose a question below or type your own. I'll help you find the information you need.")}</p>
            <Stagger className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 lg:gap-4" step={0.05}>
              {QUICK.map((q) => (
                <StaggerItem key={q.title} className="h-full">
                  <QuickCard {...q} onAsk={(text) => void send(text)} />
                </StaggerItem>
              ))}
            </Stagger>
          </>
        ) : (
          <div className="scroll-thin -mx-1 max-h-[calc(100dvh-480px)] min-h-[300px] space-y-5 overflow-y-auto px-1 py-1 max-lg:max-h-[calc(100dvh-400px)]">
            {turns.map((m, i) => (
              <motion.div
                key={i}
                initial={reduce ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}
              >
                <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-full", m.role === "user" ? "bg-gradient-to-br from-copper-400 to-copper-700 text-white" : "bg-copper-500/12 text-copper-300 ring-1 ring-copper-500/25")}>
                  {m.role === "user" ? <User className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
                </span>
                <div className={cn("min-w-0 max-w-[88%] sm:max-w-[78%]", m.role === "user" && "text-right")}>
                  <div className={cn("inline-block rounded-2xl px-4 py-3 text-left text-[15px] leading-relaxed", m.role === "user" ? "rounded-tr-md bg-gradient-to-b from-copper-500 to-copper-600 text-white shadow-[0_10px_30px_-14px_rgb(212_136_78/0.9)]" : "rounded-tl-md border border-fg/[0.07] bg-raised")}>
                    {m.role === "assistant" ? (
                      <>
                        {m.content && <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>}
                        {m.stage && <Progress stage={m.stage} startedAt={m.startedAt ?? Date.now()} reading={!!turns[i - 1]?.files?.length} />}
                        {m.error && (
                          <div className={cn("flex flex-wrap items-center gap-2 text-sm text-bad", m.content && "mt-3 border-t border-line pt-3")}>
                            <CircleAlert className="h-4 w-4 shrink-0" /> {t(m.error)}
                            {m.question && i === turns.length - 1 && (
                              <Button size="sm" variant="outline" onClick={() => void send(m.question!)} disabled={busy}>
                                <RotateCcw className="h-3.5 w-3.5" /> Try again
                              </Button>
                            )}
                          </div>
                        )}
                        {m.citations && m.content && <Citations items={m.citations} />}
                      </>
                    ) : (
                      <>
                        <p className="whitespace-pre-line">{m.content.replace(/\n\n📎[^\n]*(\n📎[^\n]*)*$/u, "")}</p>
                        {!!m.files?.length && (
                          <div className="mt-2 flex flex-wrap justify-end gap-1.5">
                            {m.files.map((f) => (
                              <span key={f} className="inline-flex max-w-56 items-center gap-1 truncate rounded-md bg-fg/15 px-2 py-0.5 text-xs"><Paperclip className="h-3 w-3" /> {f}</span>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
            {last?.role === "assistant" && last.suggestions?.length && !busy ? (
              <div className="flex flex-wrap gap-2 pl-12" aria-label={t("Suggested questions")}>
                {last.suggestions.map((s) => (
                  <button key={s} onClick={() => void send(s)} className="rounded-full border border-copper-500/30 bg-copper-500/[0.06] px-3.5 py-2 text-left text-sm text-copper-300 transition hover:-translate-y-px hover:border-copper-400 hover:bg-copper-500/12">
                    {s}
                  </button>
                ))}
              </div>
            ) : null}
            <div ref={endRef} />
          </div>
        )}

        {/* ---------------------------------------------------------- composer */}
        <div className="mt-6">
          {files.length > 0 && (
            <div className="mb-2.5 flex flex-wrap gap-2">
              {files.map((f) => (
                <span
                  key={f.key}
                  className={cn(
                    "inline-flex max-w-full items-center gap-2 rounded-xl border px-3 py-2 text-sm",
                    f.status === "error" ? "border-bad/30 bg-bad-soft text-bad" : "border-line bg-surface text-ink",
                  )}
                  title={f.error}
                >
                  {f.status === "uploading" ? <LoaderCircle className="h-4 w-4 animate-spin text-copper-600" /> : f.status === "error" ? <CircleAlert className="h-4 w-4" /> : <FileText className="h-4 w-4 text-copper-600" />}
                  <span className="max-w-48 truncate font-medium">{f.name}</span>
                  <span className="text-xs text-muted">
                    {f.status === "uploading" ? t("Reading…") : f.status === "error" ? t("Could not read") : f.pages ? t("{n} page(s)", { n: f.pages }) : t("Ready")}
                  </span>
                  <button
                    type="button"
                    onClick={() => setFiles((all) => all.filter((x) => x.key !== f.key))}
                    className="grid h-6 w-6 place-items-center rounded-full text-muted hover:bg-fg/5 hover:text-ink"
                    aria-label={t("Remove file")}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <form
            onSubmit={(e) => { e.preventDefault(); void send(input); }}
            className="flex items-end gap-1.5 rounded-[28px] border border-line-strong bg-raised py-1.5 pr-1.5 pl-4 transition focus-within:border-copper-500/60 focus-within:ring-4 focus-within:ring-copper-500/15 focus-within:shadow-[0_0_40px_-10px_rgb(212_136_78/0.5)]"
          >
            <Sparkles className="mb-3 h-5 w-5 shrink-0 text-copper-600" aria-hidden />
            <textarea
              ref={boxRef}
              value={input}
              rows={1}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              onPaste={(e) => {
                if (e.clipboardData.files.length) {
                  e.preventDefault();
                  void upload(e.clipboardData.files);
                }
              }}
              placeholder={t(listening ? "Listening… speak now" : "Ask a question or type your message...")}
              aria-label={t("Message")}
              className="min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-base text-ink outline-none placeholder:text-steel-400 sm:text-[15px]"
            />
            <input ref={fileRef} type="file" accept={ACCEPT} multiple hidden onChange={(e) => { if (e.target.files) void upload(e.target.files); e.target.value = ""; }} />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={files.length >= MAX_FILES}
              className="mb-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-full text-steel-600 transition hover:bg-fg/5 hover:text-copper-400 disabled:opacity-40"
              aria-label={t("Attach a file")}
              title={t("Attach a PDF, image or text file")}
            >
              <Paperclip className="h-5 w-5" />
            </button>
            {canSpeak && (
              <button
                type="button"
                onClick={toggleMic}
                className={cn(
                  "mb-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-full transition",
                  listening ? "animate-pulse bg-bad-soft text-bad" : "text-steel-600 hover:bg-fg/5 hover:text-copper-400",
                )}
                aria-label={t(listening ? "Stop voice input" : "Speak your question")}
                aria-pressed={listening}
              >
                {listening ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
              </button>
            )}
            {busy ? (
              <button type="button" onClick={stop} className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-fg/10 text-white transition hover:bg-fg/15" aria-label={t("Stop")}>
                <Square className="h-4 w-4" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={uploading || (!input.trim() && !readyIds.length)}
                className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-gradient-to-b from-copper-500 to-copper-600 text-white shadow-[0_8px_24px_-8px_rgb(212_136_78/0.9)] transition hover:scale-105 hover:brightness-110 active:scale-95 disabled:opacity-50 disabled:shadow-none"
                aria-label={t("Send")}
              >
                <Send className="h-5 w-5 -translate-x-px translate-y-px rotate-12" />
              </button>
            )}
          </form>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <label className="relative inline-flex h-9 items-center gap-1.5 rounded-lg border border-fg/[0.08] bg-fg/[0.03] pr-8 pl-3 text-sm font-medium text-ink">
                <Zap className="h-4 w-4 text-copper-600" aria-hidden />
                <select
                  value={lang}
                  onChange={(e) => setLang(e.target.value)}
                  className="cursor-pointer appearance-none bg-transparent pr-1 outline-none"
                  aria-label={t("Answer language")}
                >
                  {LANGS.map((l) => <option key={l.value} value={l.value}>{t(l.label)}</option>)}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 h-4 w-4 text-muted" aria-hidden />
              </label>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setHistoryOpen((o) => !o)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-fg/[0.08] bg-fg/[0.03] px-3 text-sm font-medium text-ink transition hover:border-fg/15 hover:bg-fg/[0.06]"
                  aria-expanded={historyOpen}
                >
                  <History className="h-4 w-4 text-copper-600" /> {t("History")}
                </button>
                {historyOpen && (
                  <>
                    <div className="fixed inset-0 z-30" onClick={() => setHistoryOpen(false)} />
                    <div className="absolute bottom-11 left-0 z-40 w-80 rounded-2xl border border-fg/10 bg-raised/95 p-2 shadow-[0_24px_60px_-20px_rgb(0_0_0/0.9)] backdrop-blur-xl">
                      <Button variant="secondary" size="sm" className="mb-1 w-full" onClick={newChat}>
                        <Sparkles className="h-4 w-4" /> New conversation
                      </Button>
                      <ul className="scroll-thin max-h-72 overflow-y-auto">
                        {sessions.map((s) => (
                          <li key={s.id} className={cn("group flex items-center rounded-lg", s.id === sessionId ? "bg-copper-50" : "hover:bg-fg/5")}>
                            <button onClick={() => void load(s.id)} className="min-w-0 flex-1 px-2.5 py-2 text-left">
                              <span className="block truncate text-sm">{s.title}</span>
                              <span className="text-xs text-muted">{fromNow(s.updated_at)}</span>
                            </button>
                            <button onClick={() => del.mutate(s.id)} className="mr-1 rounded p-1.5 text-muted opacity-0 group-hover:opacity-100 hover:text-bad" aria-label={t("Delete conversation")}>
                              <Trash className="h-3.5 w-3.5" />
                            </button>
                          </li>
                        ))}
                        {!sessions.length && <li className="p-3 text-sm text-muted">{t("No conversations yet.")}</li>}
                      </ul>
                    </div>
                  </>
                )}
              </div>
              <button
                type="button"
                onClick={() => setSearchOpen(true)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-fg/[0.08] bg-fg/[0.03] px-3 text-sm font-medium text-ink transition hover:border-fg/15 hover:bg-fg/[0.06]"
              >
                <Search className="h-4 w-4 text-copper-600" /> {t("Find similar records")}
              </button>
              {turns.length > 0 && (
                <button type="button" onClick={newChat} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-copper-400 hover:bg-copper-500/10">
                  <Sparkles className="h-4 w-4" /> {t("New chat")}
                </button>
              )}
            </div>
            <span className="flex items-center gap-2 text-[13px] text-steel-600" role="status">
              <span className={cn("h-2 w-2 rounded-full", statusDot.cls)} aria-hidden /> {t(statusDot.label)}
            </span>
          </div>
        </div>
      </section>

      <SimilarRecords open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}

export default function AssistantPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Assistant />
    </Suspense>
  );
}
