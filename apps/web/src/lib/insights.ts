import { FUNNEL_STAGES, type AgentRunRow, type ApplicationRow, type ApplicationStatusRow, type FitLabelRow, type JobSourceRow, type RunUsage } from "@/lib/db";

/** Score cuts the accuracy table reports; DEFAULT_CUT is highlighted. */
export const SCORE_CUTS = [50, 60, 70, 80] as const;
export const DEFAULT_CUT = 70;
/** Marked jobs needed before precision and recall mean much. */
export const MIN_LABELED = 30;
/** Claude Haiku 5.5 prices in dollars per million tokens, and per web search. */
const PRICES = { input: 0.1, output: 0.5, cacheRead: 0.01, cacheWrite: 0.125, webSearch: 0.01 };

export type ScoredJob = Pick<ApplicationRow, "fit_score" | "fit_label" | "status"> & { source: JobSourceRow };

export type LabeledScore = Pick<ApplicationRow, "fit_score" | "fit_label">;

export type CutAccuracy = {
  cut: number;
  precision: number | null;
  recall: number | null;
  truePositives: number;
  falsePositives: number;
  falseNegatives: number;
};

/**
 * Precision and recall of "score at or above the cut means a good fit" against the jobs the user marked.
 * Precision is null when no marked job reaches the cut, recall when none is marked good.
 */
export function accuracyByCut(jobs: LabeledScore[]): CutAccuracy[] {
  const marked = jobs.filter((job): job is LabeledScore & { fit_score: number; fit_label: FitLabelRow } =>
    job.fit_label !== null && job.fit_score !== null,
  );
  return SCORE_CUTS.map((cut) => {
    const truePositives = marked.filter((job) => job.fit_score >= cut && job.fit_label === "good").length;
    const falsePositives = marked.filter((job) => job.fit_score >= cut && job.fit_label === "bad").length;
    const falseNegatives = marked.filter((job) => job.fit_score < cut && job.fit_label === "good").length;
    return {
      cut,
      precision: truePositives + falsePositives ? truePositives / (truePositives + falsePositives) : null,
      recall: truePositives + falseNegatives ? truePositives / (truePositives + falseNegatives) : null,
      truePositives,
      falsePositives,
      falseNegatives,
    };
  });
}

export type SourceStats = {
  source: JobSourceRow;
  scored: number;
  averageScore: number | null;
  good: number;
  bad: number;
  pastNew: number;
};

/** Scored jobs per source, with their average score, thumbs and how many moved past "new"; busiest first. */
export function statsBySource(jobs: ScoredJob[]): SourceStats[] {
  const groups = new Map<JobSourceRow, ScoredJob[]>();
  for (const job of jobs) groups.set(job.source, [...(groups.get(job.source) ?? []), job]);
  return [...groups.entries()]
    .map(([source, group]) => {
      const scores = group.map((job) => job.fit_score).filter((score): score is number => score !== null);
      return {
        source,
        scored: group.length,
        averageScore: scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : null,
        good: group.filter((job) => job.fit_label === "good").length,
        bad: group.filter((job) => job.fit_label === "bad").length,
        pastNew: group.filter((job) => job.status !== "new").length,
      };
    })
    .sort((a, b) => b.scored - a.scored);
}

/** Dollar cost of a run's tokens and web searches at Haiku prices. */
export function runCost(usage: RunUsage | null): number {
  if (!usage) return 0;
  return (
    (usage.input_tokens * PRICES.input +
      usage.output_tokens * PRICES.output +
      usage.cache_read_input_tokens * PRICES.cacheRead +
      usage.cache_creation_input_tokens * PRICES.cacheWrite) /
      1_000_000 +
    (usage.web_search_requests ?? 0) * PRICES.webSearch
  );
}

export type CostSummary = { runs: number; total: number; perSearch: number | null; thisMonth: number };

/** Spend across the given runs, the average per finished search, and the spend since the start of this month. */
export function summarizeCosts(
  runs: Pick<AgentRunRow, "kind" | "status" | "usage" | "created_at">[],
  now = new Date(),
): CostSummary {
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const searches = runs.filter((run) => run.kind === "search" && run.status === "done");
  const total = runs.reduce((sum, run) => sum + runCost(run.usage), 0);
  return {
    runs: runs.length,
    total,
    perSearch: searches.length ? searches.reduce((sum, run) => sum + runCost(run.usage), 0) / searches.length : null,
    thisMonth: runs.filter((run) => new Date(run.created_at) >= monthStart).reduce((sum, run) => sum + runCost(run.usage), 0),
  };
}

/** A job past "new" with every status it has had, its source and the resume that scored it. */
export type FunnelJob = { statuses: ApplicationStatusRow[]; source: JobSourceRow; resume: string };

export type FunnelRow = {
  label: string;
  reached: Record<(typeof FUNNEL_STAGES)[number], number>;
  responseRate: number | null;
};

/** The furthest funnel stage a job reached, as an index into FUNNEL_STAGES, or -1 when it was never applied to. */
function furthestStage(job: FunnelJob): number {
  return Math.max(-1, ...job.statuses.map((status) => FUNNEL_STAGES.indexOf(status as (typeof FUNNEL_STAGES)[number])));
}

/**
 * How many jobs reached each stage, overall and grouped by `group`. Reaching a stage counts every stage before it,
 * so a job rejected after an interview still counts as screened. The response rate is screened or further over
 * applied. Groups with no applications are left out.
 */
export function funnel(jobs: FunnelJob[], group?: (job: FunnelJob) => string): FunnelRow[] {
  const groups = new Map<string, FunnelJob[]>();
  for (const job of jobs) {
    const label = group ? group(job) : "All";
    groups.set(label, [...(groups.get(label) ?? []), job]);
  }
  return [...groups.entries()]
    .map(([label, members]) => {
      const furthest = members.map(furthestStage);
      const reached = Object.fromEntries(
        FUNNEL_STAGES.map((stage, index) => [stage, furthest.filter((value) => value >= index).length]),
      ) as FunnelRow["reached"];
      return { label, reached, responseRate: reached.applied ? reached.screening / reached.applied : null };
    })
    .filter((row) => row.reached.applied > 0)
    .sort((a, b) => b.reached.applied - a.reached.applied);
}
