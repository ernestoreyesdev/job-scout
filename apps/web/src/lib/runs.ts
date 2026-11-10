import type { AgentRunRow, SearchRuleInput, WorkplaceTypeRow } from "@/lib/db";

/** One-line description of what a run did: the search rule, the re-score or the import. */
export function describeRun(run: AgentRunRow): { title: string; detail: string } {
  if (run.kind === "rescore") return { title: "Re-score with current resume", detail: "" };
  if (run.kind === "import") {
    const entries = (run.input as { entries?: string[] }).entries ?? [];
    return { title: "Import companies", detail: ` (${entries.length} ${entries.length === 1 ? "entry" : "entries"})` };
  }
  const input = run.input as Partial<SearchRuleInput>;
  const parts = [
    input.keywords?.join(", "),
    input.workplace_types?.length ? workplaces(input.workplace_types) : null,
    input.location,
    input.exclude?.length ? `excluding ${input.exclude.join(", ")}` : null,
    input.posted_within_days
      ? `posted in the last ${input.posted_within_days === 1 ? "day" : `${input.posted_within_days} days`}`
      : null,
    input.limit !== undefined ? `up to ${input.limit} ${input.limit === 1 ? "job" : "jobs"}` : null,
  ].filter(Boolean);
  return { title: input.company || "All companies", detail: parts.length ? ` · ${parts.join(" · ")}` : "" };
}

const WORKPLACE_LABELS = { onsite: "On-site", hybrid: "Hybrid", remote: "Remote" } as const;

/** "Hybrid", "Hybrid or remote", "On-site, hybrid or remote". */
function workplaces(types: WorkplaceTypeRow[]): string {
  const labels = types.map((type, i) => (i ? WORKPLACE_LABELS[type].toLowerCase() : WORKPLACE_LABELS[type]));
  return labels.length > 1 ? `${labels.slice(0, -1).join(", ")} or ${labels.at(-1)}` : labels[0];
}
