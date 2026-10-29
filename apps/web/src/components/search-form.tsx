"use client";

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useState, useTransition } from "react";

import { startSearch } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MAX_JOBS_PER_SEARCH, WORKPLACE_TYPES } from "@/lib/db";

const WORKPLACE_LABELS = { onsite: "On-site", hybrid: "Hybrid", remote: "Remote" } as const;

/** Starts a background search run on one company, or every company in the directory when none is given. */
export function SearchForm() {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function search(formData: FormData) {
    startTransition(async () => {
      const result = await startSearch(formData);
      setError(result.ok ? null : (result.error ?? "Could not start the search."));
    });
  }

  return (
    <form action={search} className="space-y-2">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 space-y-1">
          <Label htmlFor="keywords">Keywords (comma separated)</Label>
          <Input id="keywords" name="keywords" required placeholder="software engineer, backend" className="min-w-64" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="company">Company (optional)</Label>
          <Input id="company" name="company" placeholder="All companies" className="w-48" />
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Starting…" : "Run search"}
        </Button>
      </div>
      {/* Closed filters still submit their values; the server validates them. */}
      <details className="group text-sm">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-muted-foreground select-none hover:text-foreground">
          <SlidersHorizontal className="size-3.5" />
          Filters
          <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-2 flex flex-wrap items-end gap-6 rounded-lg border p-3">
          <fieldset className="space-y-1">
            <legend className="text-sm leading-none font-medium">Location type</legend>
            <div className="flex h-9 items-center gap-4">
              {WORKPLACE_TYPES.map((type) => (
                <label key={type} className="flex items-center gap-1.5">
                  <input type="checkbox" name="workplace" value={type} className="size-4 accent-primary" />
                  {WORKPLACE_LABELS[type]}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="space-y-1">
            <Label htmlFor="location">Location</Label>
            <Input id="location" name="location" placeholder="City or state" className="w-48" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="limit">Max jobs (1 to {MAX_JOBS_PER_SEARCH})</Label>
            <Input id="limit" name="limit" type="number" defaultValue={10} className="w-24" />
          </div>
        </div>
      </details>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  );
}
