"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState, useTransition } from "react";

import { setCareersPage, setCompanyHidden } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TableCell, TableRow } from "@/components/ui/table";
import type { DirectoryCompany } from "@/lib/db";
import { cn } from "@/lib/utils";

/**
 * One directory company with a toggle that hides it from, or returns it to,
 * this user's searches. The name links to the company's own careers page when
 * one is known, with its job board page beside it; a box takes a careers page
 * the lookup missed or got wrong.
 */
export function CompanyRow({ company, checked }: { company: DirectoryCompany; checked: string }) {
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [pending, startTransition] = useTransition();
  const link = company.careers_page_url ?? company.careers_url;
  const notFound = company.careers_page_checked_at !== null && company.careers_page_url === null;

  function saveCareersPage(formData: FormData) {
    startTransition(async () => {
      const result = await setCareersPage(company.id, formData);
      setError(result.ok ? null : (result.error ?? "Could not save this link."));
      if (result.ok) setEditing(false);
    });
  }

  function toggle() {
    startTransition(async () => {
      const result = await setCompanyHidden(company.id, !company.hidden);
      setError(result.ok ? null : (result.error ?? "Could not update this company."));
    });
  }

  return (
    <TableRow className={cn(company.hidden && "text-muted-foreground")}>
      <TableCell className="whitespace-normal">
        {link ? (
          <a
            href={link}
            target="_blank"
            rel="noreferrer"
            className={cn("font-medium hover:underline", company.hidden && "line-through")}
          >
            {company.name}
          </a>
        ) : (
          <span className={cn("font-medium", company.hidden && "line-through")}>{company.name}</span>
        )}
        {company.kind && company.kind !== "employer" && (
          <span className="ml-2 text-xs text-muted-foreground">{company.kind === "staffing" ? "Staffing agency" : "Aggregator"}</span>
        )}
        {company.hidden && <span className="ml-2 text-xs">Hidden</span>}
        <span className="ml-2 inline-flex flex-wrap gap-x-2 text-xs text-muted-foreground">
          {company.careers_page_url && company.careers_url && (
            <a href={company.careers_url} target="_blank" rel="noreferrer" className="hover:text-foreground hover:underline">
              Job board
            </a>
          )}
          {notFound && <span>Careers page not found</span>}
          {(company.careers_page_url || notFound) && !editing && (
            <button type="button" onClick={() => setEditing(true)} className="hover:text-foreground hover:underline">
              {notFound ? "Add link" : "Edit link"}
            </button>
          )}
        </span>
        {editing && (
          <form action={saveCareersPage} className="mt-2 flex flex-wrap items-center gap-2">
            <Input
              name="url"
              type="url"
              required
              defaultValue={company.careers_page_url ?? ""}
              placeholder="https://www.example.com/careers"
              aria-label={`Careers page for ${company.name}`}
              className="h-8 w-72"
            />
            <Button type="submit" size="sm" disabled={pending}>
              {pending ? "Saving…" : "Save"}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </form>
        )}
        {error && <p className="mt-1 text-sm text-destructive">{error}</p>}
      </TableCell>
      <TableCell className="text-right tabular-nums">{company.open_jobs.toLocaleString()}</TableCell>
      <TableCell>{checked}</TableCell>
      <TableCell>
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={toggle}
            disabled={pending}
            aria-label={company.hidden ? `Show ${company.name} in searches` : `Hide ${company.name} from searches`}
          >
            {company.hidden ? <Eye /> : <EyeOff />}
            {company.hidden ? "Show" : "Hide"}
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}
