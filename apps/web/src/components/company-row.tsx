"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState, useTransition } from "react";

import { setCompanyHidden } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import type { DirectoryCompany } from "@/lib/db";
import { cn } from "@/lib/utils";

/** One directory company with a toggle that hides it from, or returns it to, this user's searches. */
export function CompanyRow({ company, checked }: { company: DirectoryCompany; checked: string }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function toggle() {
    startTransition(async () => {
      const result = await setCompanyHidden(company.id, !company.hidden);
      setError(result.ok ? null : (result.error ?? "Could not update this company."));
    });
  }

  return (
    <TableRow className={cn(company.hidden && "text-muted-foreground")}>
      <TableCell className="whitespace-normal">
        {company.careers_url ? (
          <a
            href={company.careers_url}
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
          <span className="ml-2 inline-flex rounded-full bg-violet-100 px-2 py-0.5 text-xs text-violet-800 dark:bg-violet-950 dark:text-violet-300">
            {company.kind === "staffing" ? "Staffing agency" : "Aggregator"}
          </span>
        )}
        {company.hidden && (
          <span className="ml-2 inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">Hidden</span>
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
