import { WifiOff } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/brand";

export const metadata = { title: "Offline" };

export default function OfflinePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-5 bg-canvas px-6 text-center text-ink">
      <Logo />
      <WifiOff className="h-12 w-12 text-copper-400" />
      <h1 className="text-2xl font-bold">You are offline</h1>
      <p className="max-w-sm text-muted">
        Field forms you have opened before still work offline. Reports are saved on this device and synced automatically when the connection returns.
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        <Link href="/inspections/new" className="rounded-xl bg-copper-600 px-4 py-2 font-medium text-white">New inspection</Link>
        <Link href="/violations/new" className="rounded-xl border border-line-strong px-4 py-2 font-medium">Report violation</Link>
        <Link href="/attendance" className="rounded-xl border border-line-strong px-4 py-2 font-medium">Attendance</Link>
      </div>
    </main>
  );
}
