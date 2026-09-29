import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-sm font-semibold tracking-widest text-copper-600 uppercase">404</p>
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="text-muted">The page you requested does not exist or you do not have access to it.</p>
      <Link href="/dashboard" className="mt-2 rounded-xl bg-copper-600 px-4 py-2 font-medium text-white">Back to dashboard</Link>
    </main>
  );
}
