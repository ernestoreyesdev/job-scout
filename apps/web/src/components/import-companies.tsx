"use client";

import { ChevronDown, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { importCompanies } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MAX_COMPANY_IMPORT } from "@/lib/db";

/** Starts a run that adds companies to the directory from careers page URLs or company names. */
export function ImportCompanies() {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(formData: FormData) {
    startTransition(async () => {
      const result = await importCompanies(formData);
      setError(result.ok ? null : (result.error ?? "Could not start the import."));
    });
  }

  return (
    <details className="group mt-6 rounded-xl border bg-card px-4 py-3 text-sm shadow-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium select-none">
        <Plus className="size-4 text-muted-foreground" />
        Add companies
        <ChevronDown className="ml-auto size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <form action={submit} className="mt-3 space-y-2">
        <Label htmlFor="entries" className="font-normal text-muted-foreground">
          One careers page URL or company name per line, up to {MAX_COMPANY_IMPORT}. Names are checked on every job
          system the app supports; URLs work for companies whose names don&apos;t match their board.
        </Label>
        <Textarea
          id="entries"
          name="entries"
          rows={5}
          required
          placeholder={"Stripe\nhttps://jobs.lever.co/palantir\nhttps://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"}
        />
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" disabled={pending}>
            <Plus />
            {pending ? "Starting…" : "Add to directory"}
          </Button>
          {error && <span className="text-destructive">{error}</span>}
        </div>
      </form>
    </details>
  );
}
