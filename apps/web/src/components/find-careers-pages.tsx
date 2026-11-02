"use client";

import { Search } from "lucide-react";
import { useState, useTransition } from "react";

import { findCareersPages } from "@/app/actions";
import { Button } from "@/components/ui/button";

/** Starts a run that looks up careers pages for companies that never had one looked up. */
export function FindCareersPages({ count }: { count: number }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function find() {
    startTransition(async () => {
      const result = await findCareersPages();
      setError(result.ok ? null : (result.error ?? "Could not start."));
    });
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      {error && <span className="text-destructive">{error}</span>}
      <Button variant="outline" size="sm" onClick={find} disabled={pending}>
        <Search />
        {pending ? "Starting…" : `Find careers pages (${count})`}
      </Button>
    </div>
  );
}
