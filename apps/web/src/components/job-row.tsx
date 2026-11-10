"use client";

import { ChevronDown, ExternalLink, EyeOff, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { useState, useTransition } from "react";

import { analyzeGaps, deleteApplication, draftFollowUp, removeFromTracker, updateApplication } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  APPLICATION_STATUSES,
  FOLLOW_UP_DAYS,
  GHOST_JOB_DAYS,
  type FitLabelRow,
  type GapItem,
  type PostingRow,
  type TrackedJob,
} from "@/lib/db";
import { cn } from "@/lib/utils";

const PERIODS = { year: "yr", month: "mo", week: "wk", day: "day", hour: "hr" } as const;

const GAP_SECTIONS = [
  ["covered", "Covered"],
  ["weak", "Weak"],
  ["missing", "Missing"],
] as const;

/** Stack items shown as chips before the rest collapse into "+N". */
const STACK_CHIPS = 4;

const CHIP = "inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-foreground/80";
const WARNING_CHIP =
  "inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300";

/**
 * One tracked job as a card: score badge, posting link, facts as chips, warnings, a two-line fit summary, status
 * select and actions. Thumbs up or down records whether the user agrees it fits; clicking the active one clears it.
 * "Show more" opens the full summary, notes, timeline, strengths and gaps, and an on-demand gap analysis. Delete
 * removes the job everywhere; remove (Tracker only, jobs past "new") keeps it under Jobs.
 */
export function JobRow({
  job,
  showNotes,
  canRemoveFromTracker,
  staleResume,
  closedOn,
  timeline,
}: {
  job: TrackedJob;
  showNotes: boolean;
  canRemoveFromTracker: boolean;
  staleResume: boolean;
  closedOn: string | null;
  timeline: string[];
}) {
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [followUp, setFollowUp] = useState<{ subject: string; body: string } | null>(null);
  const [pending, startTransition] = useTransition();
  const { openDays, reposted, daysSinceApplied } = job.signals;
  const ghost = [
    openDays !== null && openDays >= GHOST_JOB_DAYS && `Open ${openDays} days`,
    reposted && "Reposted",
  ].filter((label): label is string => Boolean(label));
  const facts = postingFacts(job.posting);
  const stack = job.posting.tech_stack;
  const posted = job.posting.posted_at && openDays !== null ? postedAgo(openDays) : null;

  function save(field: "status" | "notes" | "fitLabel", value: string) {
    const formData = new FormData();
    formData.set(field, value);
    startTransition(async () => {
      const result = await updateApplication(job.id, formData);
      setError(result.ok ? null : (result.error ?? "Could not save."));
    });
  }

  function analyze() {
    startTransition(async () => {
      const result = await analyzeGaps(job.id);
      setError(result.ok ? null : (result.error ?? "Could not analyze this job."));
    });
  }

  function draft() {
    startTransition(async () => {
      const result = await draftFollowUp(job.id);
      setError(result.ok ? null : (result.error ?? "Could not draft a follow-up."));
      if (result.ok && result.subject !== undefined && result.body !== undefined) {
        setFollowUp({ subject: result.subject, body: result.body });
      }
    });
  }

  function remove() {
    startTransition(async () => {
      const result = await deleteApplication(job.id);
      if (!result.ok) setError(result.error ?? "Could not delete.");
    });
  }

  function hide() {
    startTransition(async () => {
      const result = await removeFromTracker(job.id);
      if (!result.ok) setError(result.error ?? "Could not remove from the Tracker.");
    });
  }

  return (
    <li
      className={cn(
        "flex flex-wrap gap-x-4 gap-y-3 rounded-xl border border-l-4 bg-card p-4 text-card-foreground shadow-xs transition-shadow hover:shadow-md",
        fitLook(job.fit_score).accent,
      )}
    >
      <ScoreBadge score={job.fit_score} />
      <div className="min-w-0 flex-1 basis-56">
        <a
          href={job.posting.url}
          target="_blank"
          rel="noreferrer"
          className="group/link inline-flex items-baseline gap-1.5 font-medium hover:underline"
        >
          {tidyCase(job.posting.title)}
          <ExternalLink className="size-3.5 shrink-0 self-center text-muted-foreground group-hover/link:text-foreground" />
        </a>
        <p className="text-sm text-muted-foreground">
          {[tidyCase(job.posting.company), job.posting.location && shortLocation(tidyCase(job.posting.location)), posted]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {(facts.length > 0 || stack.length > 0 || ghost.length > 0 || staleResume || closedOn) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {closedOn && (
              <span className="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
                Closed since {closedOn}
              </span>
            )}
            {facts.map((fact) => (
              <span key={fact} className={CHIP}>
                {fact}
              </span>
            ))}
            {stack.slice(0, STACK_CHIPS).map((tool) => (
              <span key={tool} className={CHIP}>
                {tool}
              </span>
            ))}
            {stack.length > STACK_CHIPS && (
              <span className="px-1 py-0.5 text-xs text-muted-foreground" title={stack.slice(STACK_CHIPS).join(", ")}>
                +{stack.length - STACK_CHIPS}
              </span>
            )}
            {ghost.map((label) => (
              <span key={label} className={WARNING_CHIP} title="A common sign of a ghost job">
                {label}
              </span>
            ))}
            {staleResume && <span className={WARNING_CHIP}>Scored with an older resume</span>}
          </div>
        )}
        {job.fit_summary && (
          <p className={cn("mt-2 text-sm text-muted-foreground", !expanded && "line-clamp-2")}>{job.fit_summary}</p>
        )}
        {daysSinceApplied !== null && daysSinceApplied >= FOLLOW_UP_DAYS && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className={WARNING_CHIP}>No response in {daysSinceApplied} days</span>
            {!followUp && (
              <button type="button" onClick={draft} disabled={pending} className="underline hover:text-foreground">
                {pending ? "Drafting…" : "Draft follow-up"}
              </button>
            )}
          </div>
        )}
        {followUp && (
          <div className="mt-2 space-y-1 rounded-lg border p-3 text-sm">
            <p className="font-medium">{followUp.subject}</p>
            <Textarea readOnly value={followUp.body} rows={6} />
            <div className="flex gap-3 text-xs">
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(`${followUp.subject}\n\n${followUp.body}`)}
                className="underline hover:text-foreground"
              >
                Copy
              </button>
              <button type="button" onClick={() => setFollowUp(null)} className="text-muted-foreground hover:text-foreground">
                Close
              </button>
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          aria-expanded={expanded}
        >
          {expanded ? "Show less" : "Show more"}
          <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} />
        </button>
        {expanded && (
          <div className="mt-3 space-y-3 border-t pt-3">
            {showNotes && (
              <Textarea
                defaultValue={job.notes ?? ""}
                placeholder="Notes, like a recruiter's name"
                rows={2}
                onBlur={(event) => {
                  if (event.target.value !== (job.notes ?? "")) save("notes", event.target.value);
                }}
              />
            )}
            {timeline.length > 0 && <p className="text-xs text-muted-foreground">{timeline.join(" · ")}</p>}
            {(job.strengths.length > 0 || job.gaps.length > 0) && (
              <div className="grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <p className="font-medium">Strengths</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-muted-foreground">
                    {job.strengths.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-medium">Gaps</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-muted-foreground">
                    {job.gaps.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            {job.gap_analysis ? (
              <div className="grid gap-3 text-sm sm:grid-cols-3">
                {GAP_SECTIONS.map(([key, title]) => (
                  <GapList key={key} title={title} items={job.gap_analysis![key]} />
                ))}
              </div>
            ) : (
              <Button variant="outline" size="sm" onClick={analyze} disabled={pending}>
                {pending ? "Analyzing…" : "Analyze gaps"}
              </Button>
            )}
          </div>
        )}
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
      </div>
      <div className="flex w-full shrink-0 items-center justify-between gap-2 sm:w-auto sm:flex-col sm:items-end sm:justify-start">
        <Select key={job.status} defaultValue={job.status} onValueChange={(value) => save("status", value)} disabled={pending}>
          <SelectTrigger size="sm" className="w-32 rounded-full capitalize">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {APPLICATION_STATUSES.map((status) => (
              <SelectItem key={status} value={status} className="capitalize">
                {status}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex gap-0.5">
          {(["good", "bad"] as const satisfies readonly FitLabelRow[]).map((label) => {
            const active = job.fit_label === label;
            const Icon = label === "good" ? ThumbsUp : ThumbsDown;
            return (
              <Button
                key={label}
                variant="ghost"
                size="icon-sm"
                onClick={() => save("fitLabel", active ? "" : label)}
                disabled={pending}
                aria-pressed={active}
                title={label === "good" ? "Good fit" : "Bad fit"}
                aria-label={`Mark ${job.posting.title} as a ${label} fit`}
                className={cn("text-muted-foreground", active && (label === "good" ? "text-emerald-600" : "text-destructive"))}
              >
                <Icon className={cn(active && "fill-current")} />
              </Button>
            );
          })}
          {canRemoveFromTracker && job.status !== "new" && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={hide}
              disabled={pending}
              title="Remove from Tracker (stays in Jobs)"
              aria-label={`Remove ${job.posting.title} from the Tracker, keeping it in Jobs`}
              className="text-muted-foreground"
            >
              <EyeOff />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={remove}
            disabled={pending}
            title="Delete from Tracker and Jobs"
            aria-label={`Delete ${job.posting.title} from the Tracker and Jobs`}
            className="text-muted-foreground"
          >
            <Trash2 />
          </Button>
        </div>
      </div>
    </li>
  );
}

/** Short labels for the facts read from a posting: pay, clearance, visa sponsorship and experience. */
function postingFacts(posting: PostingRow): string[] {
  const facts: string[] = [];
  if (posting.salary_min !== null || posting.salary_max !== null) {
    const money = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: posting.salary_currency ?? "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    });
    const low = posting.salary_min ?? posting.salary_max;
    const high = posting.salary_max ?? posting.salary_min;
    const range = low === high ? money.format(low!) : `${money.format(low!)}–${money.format(high!)}`;
    facts.push(posting.salary_period ? `${range}/${PERIODS[posting.salary_period]}` : range);
  }
  if (posting.clearance) facts.push(`Clearance: ${posting.clearance}`);
  if (posting.visa_sponsorship) facts.push(posting.visa_sponsorship === "yes" ? "Sponsors visas" : "No visa sponsorship");
  if (posting.years_experience !== null) facts.push(`${posting.years_experience}+ yrs`);
  return facts;
}

/** One gap analysis column: each requirement, what the resume shows for it, and how to talk about it. */
function GapList({ title, items }: { title: string; items: GapItem[] }) {
  return (
    <div>
      <p className="font-medium">
        {title} ({items.length})
      </p>
      <ul className="mt-1 space-y-2">
        {items.map((item) => (
          <li key={item.requirement}>
            <p>{item.requirement}</p>
            {item.evidence && <p className="text-xs text-muted-foreground">Resume: {item.evidence}</p>}
            <p className="text-xs text-muted-foreground">{item.suggestion}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The fit score in a circle with its label. */
function ScoreBadge({ score }: { score: number | null }) {
  const { badge, label } = fitLook(score);
  return (
    <div className="flex w-14 shrink-0 flex-col items-center gap-1" title={score === null ? undefined : `Fit score ${score} of 100`}>
      <div className={cn("flex size-11 items-center justify-center rounded-full text-sm font-semibold tabular-nums", badge)}>
        {score ?? "–"}
      </div>
      <span className="text-center text-[11px] leading-tight text-muted-foreground">{label}</span>
    </div>
  );
}

/** Colors and label for a fit score: green from 70, amber from 50, gray below and when unscored. */
function fitLook(score: number | null): { badge: string; accent: string; label: string } {
  if (score === null) return { badge: "bg-muted text-muted-foreground", accent: "border-l-border", label: "Not scored" };
  if (score >= 70) {
    return {
      badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
      accent: "border-l-emerald-500",
      label: "Strong fit",
    };
  }
  if (score >= 50) {
    return {
      badge: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
      accent: "border-l-amber-400",
      label: "Possible fit",
    };
  }
  return { badge: "bg-muted text-muted-foreground", accent: "border-l-muted-foreground/30", label: "Weak fit" };
}

function postedAgo(days: number): string {
  if (days === 0) return "posted today";
  if (days === 1) return "posted yesterday";
  if (days < 14) return `posted ${days} days ago`;
  if (days < 60) return `posted ${Math.floor(days / 7)} weeks ago`;
  return `posted ${Math.floor(days / 30)} months ago`;
}

/**
 * Text a source sent in all capitals, in title case. Words of up to three letters stay capitalized as likely
 * acronyms ("US", "NY", "AWS"), except the common words in SHORT_WORDS.
 */
function tidyCase(text: string): string {
  if (text !== text.toUpperCase() || !/[A-Z]{4}/.test(text)) return text;
  return text.replace(/[A-Z]+/g, (word) =>
    word.length <= 3 && !SHORT_WORDS.has(word) ? word : word[0] + word.slice(1).toLowerCase(),
  );
}

const SHORT_WORDS = new Set(["NEW", "THE", "AND", "FOR", "OF", "IN", "AT", "TO", "SAN", "LOS", "LAS", "ALL", "ANY"]);

/** A location without a trailing country name for the US, which every search is limited to. */
function shortLocation(location: string): string {
  return location.replace(/,\s*(United States( of America)?|USA|US)$/i, "") || location;
}
