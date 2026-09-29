import type { ReactNode } from "react";

/** Public marketing shell — no session, no app chrome. */
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-canvas">{children}</div>;
}
