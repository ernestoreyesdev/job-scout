"use client";

import { Building2, ChevronDown, Search, SlidersHorizontal } from "lucide-react";
import { useState, useTransition, type ReactNode } from "react";

import { startSearch } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MAX_JOBS_PER_SEARCH, MIN_SCORES, POSTED_WITHIN_DAYS, WORKPLACE_TYPES } from "@/lib/db";

const WORKPLACE_LABELS = { onsite: "On-site", hybrid: "Hybrid", remote: "Remote" } as const;

const SELECT = "h-9 w-full rounded-md border border-input bg-background px-2 text-sm shadow-xs disabled:opacity-50";

/**
 * Starts a background search run on one company, or every company in the directory when none is given. The fields
 * clear after each search. Scoring against the resume is only available once one is uploaded.
 */
export function SearchForm({ hasResume }: { hasResume: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const [keywordError, setKeywordError] = useState(false);
  const [pending, startTransition] = useTransition();

  function search(formData: FormData) {
    if (!String(formData.get("keywords") ?? "").trim()) {
      setKeywordError(true);
      return;
    }
    startTransition(async () => {
      const result = await startSearch(formData);
      setError(result.ok ? null : (result.error ?? "Could not start the search."));
    });
  }

  return (
    <form
      action={search}
      noValidate
      autoComplete="off"
      className="flex flex-wrap items-start gap-x-2 gap-y-3 rounded-xl border bg-card p-4 shadow-xs"
    >
      <div className="min-w-64 flex-1 space-y-1.5">
        <Label htmlFor="keywords">Job titles or keywords</Label>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="keywords"
            name="keywords"
            aria-describedby={keywordError ? "keywords-error" : "keywords-hint"}
            aria-invalid={keywordError || undefined}
            onChange={() => setKeywordError(false)}
            className="h-10 pl-9 text-base"
          />
        </div>
        {keywordError ? (
          <p id="keywords-error" className="text-sm text-destructive">
            Enter a job title or keyword.
          </p>
        ) : (
          <p id="keywords-hint" className="text-xs text-muted-foreground">
            Separate several with commas. Leave Company empty to search every company.
          </p>
        )}
      </div>
      <div className="w-full space-y-1.5 sm:w-52">
        <Label htmlFor="company">Company (optional)</Label>
        <div className="relative">
          <Building2 className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input id="company" name="company" className="h-10 pl-9" />
        </div>
      </div>
      <div className="order-last flex w-full items-center gap-3 sm:order-none sm:w-auto sm:pt-5">
        <label
          className="inline-flex h-10 shrink-0 cursor-pointer items-center gap-2 px-1 text-sm text-muted-foreground"
          title={hasResume ? undefined : "Upload a resume to score jobs"}
        >
          Score with my resume
          <input
            type="checkbox"
            name="score"
            defaultChecked={hasResume}
            disabled={!hasResume}
            className="peer sr-only"
          />
          <span className="relative h-5 w-9 rounded-full bg-muted-foreground/30 transition-colors peer-checked:bg-primary peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50 peer-disabled:opacity-50 after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-background after:shadow-xs after:transition-transform peer-checked:after:translate-x-4" />
        </label>
        <Button type="submit" disabled={pending} className="h-10 flex-1 px-5 sm:flex-none">
          {pending ? "Starting…" : "Find jobs"}
        </Button>
      </div>
      {/* Closed filters still submit their values; the server validates them. */}
      <details className="group basis-full text-sm">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-muted-foreground select-none hover:text-foreground">
          <SlidersHorizontal className="size-3.5" />
          More filters
          <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-3 grid gap-5 sm:grid-cols-3">
          <FilterGroup title="Where">
            <fieldset className="col-span-2 space-y-1.5 sm:col-span-1">
              <legend className="mb-1.5 text-sm leading-none font-medium">Location type</legend>
              <div className="flex h-9 flex-wrap items-center gap-x-4 gap-y-1">
                {WORKPLACE_TYPES.map((type) => (
                  <label key={type} className="flex items-center gap-1.5">
                    <input type="checkbox" name="workplace" value={type} className="size-4 accent-primary" />
                    {WORKPLACE_LABELS[type]}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="col-span-2 space-y-1.5 sm:col-span-1">
              <Label htmlFor="location">Location</Label>
              <Input id="location" name="location" />
            </div>
          </FilterGroup>
          <FilterGroup title="Which jobs">
            <div className="space-y-1.5">
              <Label htmlFor="postedWithin">Posted</Label>
              <select id="postedWithin" name="postedWithin" defaultValue="" className={SELECT}>
                <option value="">Any time</option>
                {POSTED_WITHIN_DAYS.map((days) => (
                  <option key={days} value={days}>
                    {days === 1 ? "Last day" : `Last ${days} days`}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exclude">Leave out</Label>
              <Input id="exclude" name="exclude" />
            </div>
          </FilterGroup>
          <FilterGroup title="Results">
            <div className="space-y-1.5">
              <Label htmlFor="limit">Max jobs</Label>
              <Input id="limit" name="limit" type="number" min={1} max={MAX_JOBS_PER_SEARCH} defaultValue={10} />
            </div>
            <div className="space-y-1.5" title={hasResume ? "Used when Score with my resume is on" : "Upload a resume to score jobs"}>
              <Label htmlFor="minScore">Min score</Label>
              <select id="minScore" name="minScore" defaultValue="" disabled={!hasResume} className={SELECT}>
                <option value="">Any score</option>
                {MIN_SCORES.map((score) => (
                  <option key={score} value={score}>
                    {score}+ ({score >= 70 ? "strong fit" : "possible fit or better"})
                  </option>
                ))}
              </select>
            </div>
          </FilterGroup>
        </div>
      </details>
      {error && <p className="order-last basis-full text-sm text-destructive">{error}</p>}
    </form>
  );
}

/** A titled group of filters: two to a row on phones, stacked in its own column from the sm breakpoint up. */
function FilterGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-1">{children}</div>
    </section>
  );
}
