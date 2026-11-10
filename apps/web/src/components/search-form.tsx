"use client";

import { Building2, ChevronDown, Search, SlidersHorizontal } from "lucide-react";
import { useState, useTransition } from "react";

import { startSearch } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MAX_JOBS_PER_SEARCH, POSTED_WITHIN_DAYS, WORKPLACE_TYPES } from "@/lib/db";

const WORKPLACE_LABELS = { onsite: "On-site", hybrid: "Hybrid", remote: "Remote" } as const;

/**
 * Starts a background search run on one company, or every company in the directory when none is given. Scoring
 * against the resume is on by default and only available once one is uploaded.
 */
export function SearchForm({ hasResume }: { hasResume: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function search(formData: FormData) {
    startTransition(async () => {
      const result = await startSearch(formData);
      setError(result.ok ? null : (result.error ?? "Could not start the search."));
    });
  }

  return (
    <form action={search} className="rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-64 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="keywords"
            name="keywords"
            required
            aria-label="Keywords, comma separated"
            placeholder="Job titles or keywords, like software engineer, backend"
            className="h-10 pl-9 text-base"
          />
        </div>
        <div className="relative w-full sm:w-52">
          <Building2 className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input id="company" name="company" aria-label="Company" placeholder="All companies" className="h-10 pl-9" />
        </div>
        <Button type="submit" disabled={pending} className="h-10 px-5">
          {pending ? "Starting…" : "Find jobs"}
        </Button>
      </div>
      <div className="mt-3 flex items-start gap-4 text-sm">
      {/* Closed filters still submit their values; the server validates them. */}
      <details className="group min-w-0 flex-1">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-muted-foreground select-none hover:text-foreground">
          <SlidersHorizontal className="size-3.5" />
          More filters
          <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-3 grid gap-4 rounded-lg bg-muted/40 p-3 sm:grid-cols-2 lg:grid-cols-5">
          <fieldset className="space-y-1.5 lg:col-span-2">
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
          <div className="space-y-1.5">
            <Label htmlFor="location">Location</Label>
            <Input id="location" name="location" placeholder="Tampa or Florida" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="exclude">Leave out</Label>
            <Input id="exclude" name="exclude" placeholder="intern, manager" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="postedWithin">Posted</Label>
              <select
                id="postedWithin"
                name="postedWithin"
                defaultValue=""
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm shadow-xs"
              >
                <option value="">Any time</option>
                {POSTED_WITHIN_DAYS.map((days) => (
                  <option key={days} value={days}>
                    {days === 1 ? "Last day" : `Last ${days} days`}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="limit">Max jobs</Label>
              <Input id="limit" name="limit" type="number" min={1} max={MAX_JOBS_PER_SEARCH} defaultValue={10} />
            </div>
          </div>
        </div>
      </details>
      <label
        className="inline-flex shrink-0 cursor-pointer items-center gap-2 text-muted-foreground"
        title={hasResume ? undefined : "Upload a resume to score jobs"}
      >
        Score with my resume
        <input type="checkbox" name="score" defaultChecked={hasResume} disabled={!hasResume} className="peer sr-only" />
        <span className="relative h-5 w-9 rounded-full bg-muted-foreground/30 transition-colors peer-checked:bg-primary peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50 peer-disabled:opacity-50 after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-background after:shadow-xs after:transition-transform peer-checked:after:translate-x-4" />
      </label>
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </form>
  );
}
