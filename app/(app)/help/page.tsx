"use client";

import { ChevronDown, ClipboardCheck, FileCheck2, MessageSquareWarning, TriangleAlert, WifiOff, Wrench, ChartColumn } from "lucide-react";
import Link from "next/link";
import { useSession } from "@/components/session";
import { Card, PageHeader } from "@/components/ui";
import { roleLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

// The four steps every record goes through, in the words people use on site.
const FLOW = [
  { icon: ClipboardCheck, title: "1. Inspect", body: "Visit the site and record what you see, with photos. Works without internet." },
  { icon: TriangleAlert, title: "2. Report the problem", body: "Anything unsafe or against the rules becomes a violation with a deadline." },
  { icon: Wrench, title: "3. Fix and check", body: "Assign someone to fix it. Another person checks the fix before it is closed." },
  { icon: ChartColumn, title: "4. Monitor", body: "Dashboards and monthly reports show what is on track and what needs attention." },
];

const ROLE_TASKS: Record<string, { label: string; href: string }[]> = {
  mine_official: [
    { label: "Record today's inspection", href: "/inspections/new" },
    { label: "Report a violation you found", href: "/violations/new" },
    { label: "Assign and check corrective actions", href: "/corrective-actions" },
    { label: "Complete compliance items before they are due", href: "/compliance" },
    { label: "Handle grievances raised at your mine", href: "/grievances" },
    { label: "Record production and environment readings", href: "/production" },
  ],
  corporate: [
    { label: "See which mines need attention", href: "/dashboard" },
    { label: "Review escalated violations", href: "/violations" },
    { label: "Verify new contractors", href: "/contractors" },
    { label: "Generate the monthly report", href: "/reports" },
    { label: "Check production against target", href: "/production" },
  ],
  regulator: [
    { label: "Review open violations across mines", href: "/violations" },
    { label: "Download statutory reports", href: "/reports" },
    { label: "Check the audit log", href: "/audit" },
    { label: "Look at environment readings", href: "/environment" },
  ],
  contractor: [
    { label: "Complete the fixes assigned to you", href: "/corrective-actions" },
    { label: "Record your workers' attendance", href: "/attendance" },
    { label: "Raise a grievance", href: "/grievances" },
  ],
  admin: [
    { label: "Approve new users and set their roles", href: "/users" },
    { label: "Check the audit log", href: "/audit" },
    { label: "See the whole picture on the dashboard", href: "/dashboard" },
  ],
};

const FAQ = [
  { q: "What happens if I have no internet at the mine?", a: "Inspections, violations and attendance are saved on your phone and sent automatically when the signal returns. The top of the screen shows how many are waiting." },
  { q: "What happens if a deadline is missed?", a: "The item is escalated automatically — first to mine management, then to the subsidiary, then to head office — and each level is notified." },
  { q: "How do I switch to Hindi?", a: "Use the EN / हि switch in your profile menu (top right on a computer, Menu on a phone). Your choice is remembered." },
  { q: "Who can see my mine's data?", a: "Only people at your mine, your subsidiary's management, head office and the regulator. Contractors see only the mines they work at." },
  { q: "Can anyone change a record after it is saved?", a: "No record is lost. Every change is kept in the audit log with who made it and when, and old entries cannot be edited." },
  { q: "I forgot my password.", a: "Use “Forgot Password?” on the sign-in page, or ask your administrator to reset it." },
];

export default function HelpPage() {
  const { me } = useSession();
  const { t } = useI18n();
  const tasks = ROLE_TASKS[me.role] ?? [];
  return (
    <div className="space-y-5">
      <PageHeader title="Help" subtitle="How Lumen works, and what to do next" />

      <Card className="p-5">
        <h2 className="text-[17px] font-semibold">{t("How work moves through Lumen")}</h2>
        <ol className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {FLOW.map(({ icon: Icon, title, body }) => (
            <li key={title} className="rounded-xl bg-canvas p-4">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-copper-600 text-white"><Icon className="h-5 w-5" /></span>
              <p className="mt-3 font-semibold">{t(title)}</p>
              <p className="mt-1 text-sm text-muted">{t(body)}</p>
            </li>
          ))}
        </ol>
      </Card>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-[17px] font-semibold">{t("Your usual tasks")}</h2>
          <p className="mt-1 text-sm text-muted">{t(roleLabel[me.role] ?? me.role)}</p>
          <ul className="mt-3 divide-y divide-line">
            {tasks.map((task) => (
              <li key={task.label}>
                <Link href={task.href} className="flex min-h-12 items-center justify-between gap-3 py-2.5 text-[15px] hover:text-copper-400">
                  {t(task.label)} <span aria-hidden>→</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-5">
          <h2 className="text-[17px] font-semibold">{t("Common questions")}</h2>
          <div className="mt-2 divide-y divide-line">
            {FAQ.map((f) => (
              <details key={f.q} className="group py-1">
                <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 text-[15px] font-medium">
                  {t(f.q)}
                  <ChevronDown className="h-5 w-5 shrink-0 text-muted transition group-open:rotate-180" />
                </summary>
                <p className="pb-3 text-sm leading-relaxed text-muted">{t(f.a)}</p>
              </details>
            ))}
          </div>
        </Card>
      </div>

      <Card className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-3">
        {[
          { icon: FileCheck2, text: "Deadlines: critical problems must have a fix assigned within 4 hours, high within 24 hours, medium within 3 days." },
          { icon: MessageSquareWarning, text: "Grievances can be raised anonymously; only administrators can see who raised them." },
          { icon: WifiOff, text: "On a phone, the + button at the bottom creates an inspection, violation, grievance or reading in one tap." },
        ].map(({ icon: Icon, text }) => (
          <div key={text} className="flex gap-3 text-sm">
            <Icon className="mt-0.5 h-5 w-5 shrink-0 text-copper-600" />
            <p className="text-muted">{t(text)}</p>
          </div>
        ))}
      </Card>
    </div>
  );
}
