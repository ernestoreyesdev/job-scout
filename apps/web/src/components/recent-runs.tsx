import { ChevronDown } from "lucide-react";

import type { AgentRunRow } from "@/lib/db";
import { describeRun } from "@/lib/runs";

// Swedish formatting is ISO: "2026-11-13 21:37".
const WHEN = new Intl.DateTimeFormat("sv-SE", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Collapsible list of past searches and re-scores with what each one did. */
export function RecentRuns({ runs }: { runs: AgentRunRow[] }) {
  if (runs.length === 0) return null;

  return (
    <details className="group mt-1.5 text-sm">
      <summary className="ml-auto block w-fit cursor-pointer list-none px-1 text-xs text-muted-foreground select-none hover:text-foreground">
        Recent searches ({runs.length})
        <ChevronDown className="ml-1 inline size-3.5 align-[-2px] transition-transform group-open:rotate-180" />
      </summary>
      <ul className="mt-2 divide-y rounded-lg border">
        {runs.map((run) => {
          const { title, detail } = describeRun(run);
          return (
            <li key={run.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
              <span className="basis-full text-muted-foreground tabular-nums sm:w-36 sm:shrink-0 sm:basis-auto">{WHEN.format(new Date(run.created_at))}</span>
              <span className="min-w-0 basis-full sm:basis-0 sm:flex-1">
                <span className="font-medium">{title}</span>
                {detail}
                <span className={run.status === "failed" ? "block text-destructive" : "block text-muted-foreground"}>
                  {run.status === "failed" ? run.error : (run.progress ?? run.status)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </details>
  );
}
