"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="mx-auto max-w-lg py-20 text-center">
      <h1 className="text-xl font-bold">Something went wrong</h1>
      <p className="mt-2 text-sm text-muted">The page failed to render. Your data is safe; try again or reload.</p>
      {error.digest && <p className="mt-1 font-mono text-xs text-muted">Reference: {error.digest}</p>}
      <Button className="mt-5" onClick={reset}>Try again</Button>
    </div>
  );
}
