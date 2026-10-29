import type { AgentRunRow, SearchRuleInput } from "@/lib/db";

/** One-line description of what a run did: the search rule, or the re-score. */
export function describeRun(run: AgentRunRow): { title: string; detail: string } {
  if (run.kind === "rescore") return { title: "Re-score with current resume", detail: "" };
  const input = run.input as Partial<SearchRuleInput>;
  const detail = [
    input.keywords?.length ? ` for ${input.keywords.join(", ")}` : "",
    input.workplace_types?.length ? `, location_type=${input.workplace_types.join("/")}` : "",
    input.location ? `, location=${input.location}` : "",
    input.exclude?.length ? `, exclude=${input.exclude.join("/")}` : "",
    input.posted_within_days ? `, posted_within=${input.posted_within_days}d` : "",
    input.limit !== undefined ? `, max_jobs=${input.limit}` : "",
  ].join("");
  return { title: input.company || "All companies", detail };
}
