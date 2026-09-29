"use client";

import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole, UserRound } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { CopperText, Spark, Split } from "@/components/fx";
import { FadeContent } from "@/components/motion";
import { useI18n } from "@/lib/i18n";

const SSO_ERRORS: Record<string, string> = {
  sso_unavailable: "Government SSO is not available right now.",
  sso_denied: "Sign-in was cancelled at the SSO provider.",
  sso_failed: "Government SSO sign-in failed.",
};

export function LoginForm() {
  const params = useSearchParams();
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(() => {
    const code = params.get("error");
    if (!code) return null;
    return [SSO_ERRORS[code] ?? "Sign-in failed.", params.get("detail")].filter(Boolean).join(" ");
  });
  const [sso, setSso] = useState<{ enabled: boolean; provider_name: string } | null>(null);
  const next = params.get("next");
  const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";

  useEffect(() => {
    fetch("/api/proxy/auth/sso/config")
      .then((r) => (r.ok ? r.json() : null))
      .then(setSso)
      .catch(() => setSso(null));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError(t("Enter your username and password."));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(res.status === 429 ? data.detail ?? "Too many attempts. Please wait a minute." : data.detail ?? "Sign-in failed");
        return;
      }
      window.location.assign(safeNext);
    } catch {
      setError("Cannot reach the server. Check your connection.");
    } finally {
      setLoading(false);
    }
  }

  const field =
    "peer h-14 w-full rounded-2xl border border-line-strong bg-raised/80 pl-[52px] text-base text-ink outline-none backdrop-blur transition placeholder:text-steel-400 hover:border-steel-300 focus:border-copper-500 focus:bg-raised focus:ring-4 focus:ring-copper-500/15 sm:text-[15px]";
  const icon =
    "pointer-events-none absolute top-1/2 left-5 h-5 w-5 -translate-y-1/2 text-steel-500 transition peer-focus:text-copper-400";

  return (
    <div>
      <h1 className="text-[2.4rem] leading-[1.05] font-bold tracking-[-0.035em] text-ink sm:text-[2.9rem]">
        <Split text={t("Welcome to")} by="chars" delay={20} /> <CopperText>Lumen</CopperText>
      </h1>
      <FadeContent delay={0.25}>
        <p className="mt-3 text-[15px] leading-relaxed text-muted sm:text-base">
          {t("A smart governance and compliance monitoring platform for coal mines under the Ministry of Coal.")}
        </p>
      </FadeContent>

      <FadeContent delay={0.35} y={12}>
        <form onSubmit={onSubmit} className="mt-8 space-y-3.5" noValidate>
          <div className="relative">
            <input
              id="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("Username / Email ID")}
              aria-label={t("Username / Email ID")}
              className={`${field} pr-4`}
            />
            <UserRound className={icon} aria-hidden />
          </div>

          <div className="relative">
            <input
              id="password"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("Password")}
              aria-label={t("Password")}
              className={`${field} pr-14`}
            />
            <LockKeyhole className={icon} aria-hidden />
            <button
              type="button"
              onClick={() => setShow((v) => !v)}
              className="absolute top-1/2 right-2.5 grid h-10 w-10 -translate-y-1/2 place-items-center rounded-xl text-steel-500 transition hover:bg-fg/5 hover:text-ink"
              aria-label={show ? t("Hide password") : t("Show password")}
            >
              {show ? <Eye className="h-5 w-5" /> : <EyeOff className="h-5 w-5" />}
            </button>
          </div>

          <div className="flex justify-end">
            <Link href="/forgot-password" className="text-sm font-semibold text-copper-400 transition hover:text-copper-300">
              {t("Forgot Password?")}
            </Link>
          </div>

          <AnimatePresence>
            {error && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto", x: [0, -6, 6, -3, 3, 0] }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.35 }}
                className="overflow-hidden rounded-2xl border border-bad/25 bg-bad-soft px-4 py-3 text-sm text-bad"
                role="alert"
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          <Spark>
            <button
              type="submit"
              disabled={loading}
              className="group relative flex h-14 w-full items-center justify-center gap-2.5 overflow-hidden rounded-2xl bg-gradient-to-b from-copper-500 to-copper-600 text-base font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_16px_40px_-14px_rgb(212_136_78/0.9)] transition hover:brightness-110 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {/* light sweep on hover */}
              <span aria-hidden className="absolute inset-y-0 -left-1/3 w-1/3 -skew-x-12 bg-white/20 opacity-0 blur-md transition-all duration-700 group-hover:left-full group-hover:opacity-100" />
              {loading ? <LoaderCircle className="h-5 w-5 animate-spin" /> : null}
              {loading ? t("Signing in…") : t("Login")}
              {!loading && <ArrowRight className="h-5 w-5 transition group-hover:translate-x-1" />}
            </button>
          </Spark>
        </form>

        <div className="my-6 flex items-center gap-4 text-sm text-steel-500">
          <span className="h-px flex-1 bg-gradient-to-r from-transparent to-fg/10" />
          {t("or continue with")}
          <span className="h-px flex-1 bg-gradient-to-l from-transparent to-fg/10" />
        </div>

        {sso?.enabled ? (
          <a href={`/api/auth/sso/start?return_to=${encodeURIComponent(safeNext)}`} className={SSO_BUTTON}>
            <SsoBadge />
            {t("Login with Government SSO")}
            <span className="sr-only">({sso.provider_name})</span>
          </a>
        ) : (
          <button type="button" onClick={() => setError(t("Single sign-on is not configured for this deployment."))} className={SSO_BUTTON}>
            <SsoBadge />
            {t("Login with Government SSO")}
          </button>
        )}

        <p className="mt-8 text-center text-sm text-muted">
          {t("Not a member?")}{" "}
          <Link href="/register" className="font-medium text-ink underline-offset-4 transition hover:text-copper-400 hover:underline">
            {t("Contact your administrator")}
          </Link>
        </p>
      </FadeContent>
    </div>
  );
}

const SSO_BUTTON =
  "flex h-14 w-full items-center justify-center gap-3 rounded-2xl border border-line-strong bg-fg/[0.03] text-[15px] font-semibold text-ink transition hover:border-copper-500/40 hover:bg-fg/[0.06]";

/** Round "SSO" mark in the national colours, as on the approved design. */
function SsoBadge({ muted }: { muted?: boolean }) {
  return (
    <span
      aria-hidden
      className={`grid h-7 w-7 place-items-center rounded-full border-2 text-[9px] font-extrabold tracking-tight ${
        muted ? "border-steel-300 text-steel-400" : "border-[#FF9933] bg-white text-[#138808]"
      }`}
      style={muted ? undefined : { borderBottomColor: "#138808", borderRightColor: "#138808" }}
    >
      SSO
    </span>
  );
}
