"use server";

import { revalidatePath } from "next/cache";
import { unstable_rethrow } from "next/navigation";

import {
  APPLICATION_STATUSES,
  BYTES_PER_MB,
  DAILY_SEARCH_CHOICES,
  DAILY_SEARCH_SCAN,
  FIT_LABELS,
  MAX_COMPANY_IMPORT,
  MAX_FIELD_LENGTH,
  MAX_IMPORT_ENTRY_LENGTH,
  MAX_LESSON_LENGTH,
  MAX_JOBS_PER_SEARCH,
  MAX_RESUME_MB,
  MIN_SCORES,
  OUTSIDE_STATUSES,
  POSTED_WITHIN_DAYS,
  RESUME_TYPES,
  THEMES,
  WORKPLACE_TYPES,
  type ApplicationStatusRow,
  type FitLabelRow,
  type AgentRunRow,
  type RescoreScope,
  type SearchRuleInput,
  type ThemeRow,
  type WorkplaceTypeRow,
} from "@/lib/db";
import { AgentError, callAgent } from "@/lib/agent";
import { getSignedInSource } from "@/lib/repository";
import { describeSearch, sameRule } from "@/lib/runs";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

const MAX_RESUME_BYTES = MAX_RESUME_MB * BYTES_PER_MB;
const RESUME_FILE = new RegExp(`\\.(${Object.keys(RESUME_TYPES).join("|")})$`, "i");

/** Runs an action, turning thrown validation, database or agent errors into a result. */
async function run(paths: string | string[], work: () => Promise<void>): Promise<ActionResult> {
  try {
    await work();
    for (const path of [paths].flat()) revalidatePath(path);
    return { ok: true };
  } catch (error) {
    // Rethrows Next.js control flow, such as a redirect to sign in.
    unstable_rethrow(error);
    return { ok: false, error: error instanceof Error ? error.message : "Something went wrong." };
  }
}

function text(value: FormDataEntryValue | null): string {
  return typeof value === "string" ? value.trim() : "";
}

/** Saves or replaces the shared Anthropic key runs use when a user has none; admins only. */
export async function saveSharedKey(formData: FormData): Promise<ActionResult> {
  return run("/admin", async () => {
    const apiKey = text(formData.get("apiKey"));
    if (!apiKey) throw new Error("Paste an Anthropic API key.");
    await callAgent("/admin/anthropic-key", { method: "PUT", body: { api_key: apiKey } });
  });
}

/** Removes the shared Anthropic key; admins only. */
export async function removeSharedKey(): Promise<ActionResult> {
  return run("/admin", async () => {
    await callAgent("/admin/anthropic-key", { method: "DELETE" });
  });
}

export async function uploadResume(formData: FormData): Promise<ActionResult> {
  return run("/resume", async () => {
    const file = formData.get("file");
    if (!(file instanceof File) || file.size === 0) throw new Error("Choose a PDF or .docx file.");
    if (!RESUME_FILE.test(file.name)) throw new Error("Only PDF and .docx resumes are supported.");
    if (file.size > MAX_RESUME_BYTES) throw new Error(`Resumes must be under ${MAX_RESUME_MB} MB.`);

    const { repository } = await getSignedInSource();
    const resume = await repository.uploadResume(file);
    await callAgent(`/resumes/${resume.id}/extract`, { method: "POST" });
  });
}

export async function startSearch(formData: FormData): Promise<ActionResult> {
  return run("/tracker", async () => {
    const keywords = text(formData.get("keywords"))
      .split(",")
      .map((keyword) => keyword.trim())
      .filter(Boolean);
    if (keywords.length === 0) throw new Error("Enter at least one keyword.");

    const company = text(formData.get("company")) || null;
    if (company && company.length > MAX_FIELD_LENGTH) throw new Error(`Company names must be under ${MAX_FIELD_LENGTH} characters.`);

    const workplaceTypes = formData.getAll("workplace").map(String);
    if (!workplaceTypes.every((type) => WORKPLACE_TYPES.includes(type as WorkplaceTypeRow))) {
      throw new Error("Unknown location type.");
    }

    const location = text(formData.get("location")) || null;
    if (location && location.length > MAX_FIELD_LENGTH) throw new Error(`Locations must be under ${MAX_FIELD_LENGTH} characters.`);

    const limit = Number(text(formData.get("limit")));
    if (!Number.isInteger(limit) || limit < 1 || limit > MAX_JOBS_PER_SEARCH) {
      throw new Error(`Max jobs must be a whole number from 1 to ${MAX_JOBS_PER_SEARCH}.`);
    }

    const exclude = text(formData.get("exclude"))
      .split(",")
      .map((word) => word.trim())
      .filter(Boolean);

    const postedWithin = text(formData.get("postedWithin"));
    const postedWithinDays = postedWithin ? Number(postedWithin) : null;
    if (postedWithinDays !== null && !(POSTED_WITHIN_DAYS as readonly number[]).includes(postedWithinDays)) {
      throw new Error("Unknown posted-within period.");
    }

    const minScoreValue = text(formData.get("minScore"));
    const minScore = minScoreValue ? Number(minScoreValue) : null;
    if (minScore !== null && !(MIN_SCORES as readonly number[]).includes(minScore)) {
      throw new Error("Unknown minimum score.");
    }

    const rule: SearchRuleInput = {
      keywords,
      company,
      workplace_types: workplaceTypes as WorkplaceTypeRow[],
      location,
      limit,
      web_lookup: false,
      exclude,
      posted_within_days: postedWithinDays as SearchRuleInput["posted_within_days"],
      score: formData.get("score") === "on",
      min_score: minScore as SearchRuleInput["min_score"],
    };
    await callAgent("/runs/search", { method: "POST", body: rule });
  });
}

export async function updateApplication(id: string, formData: FormData): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    const status = formData.get("status");
    const notes = formData.get("notes");
    const fitLabel = formData.get("fitLabel");
    if (status !== null && !APPLICATION_STATUSES.includes(status as ApplicationStatusRow)) {
      throw new Error("Unknown status.");
    }
    if (fitLabel !== null && fitLabel !== "" && !FIT_LABELS.includes(fitLabel as FitLabelRow)) {
      throw new Error("Unknown fit label.");
    }

    const { repository } = await getSignedInSource();
    await repository.updateApplication(id, {
      ...(status !== null && { status: status as ApplicationStatusRow }),
      ...(notes !== null && { notes: text(notes) || null }),
      ...(fitLabel !== null && { fit_label: (fitLabel || null) as FitLabelRow | null }),
    });
  });
}

/** Starts a new run with the same rule as a failed or stopped one, optionally looking the company up on the web. */
export async function rerunSearch(runId: string, webLookup = false): Promise<ActionResult> {
  return run("/tracker", async () => {
    const { repository } = await getSignedInSource();
    const previous = await repository.getRun(runId);
    if (!previous) throw new Error("Search not found.");
    if (previous.status !== "failed" && previous.status !== "stopped") {
      throw new Error("Only failed or stopped searches can be re-run.");
    }

    const input = previous.input as Partial<SearchRuleInput>;
    if (!input.keywords?.length) throw new Error("This search has no keywords. Start a new one instead.");

    // The agent fills fields older runs lack with its own defaults.
    const rule = { ...input, web_lookup: webLookup || (input.web_lookup ?? false) };
    await callAgent("/runs/search", { method: "POST", body: rule });
  });
}

export async function deleteApplication(id: string): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    const { repository } = await getSignedInSource();
    await repository.deleteApplication(id);
  });
}

/** Empties the Tracker; rated jobs and jobs past "new" stay under Jobs. */
export async function clearTracker(): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    const { repository } = await getSignedInSource();
    await repository.clearTracker();
  });
}

/** Hides a directory company from this user's searches across all companies, or shows it again. */
export async function setCompanyHidden(companyId: string, hidden: boolean): Promise<ActionResult> {
  return run("/companies", async () => {
    const { repository } = await getSignedInSource();
    await repository.setCompanyHidden(companyId, hidden);
  });
}

/**
 * Marks a search to run each morning and email its new strong matches, or unmarks it. A search is a past run, or a
 * marked search too old to be among the recent runs, which can only be unmarked.
 */
export async function setSearchAlert(search: { runId: string | null; alertId: string | null }, on: boolean): Promise<ActionResult> {
  return run([], async () => {
    const { repository } = await getSignedInSource();
    if (!search.runId) {
      if (!on && search.alertId) await repository.deleteSearchAlert(search.alertId);
      return;
    }
    const [past, alerts] = await Promise.all([repository.getRun(search.runId), repository.listSearchAlerts()]);
    if (!past || past.kind !== "search") throw new Error("Search not found.");
    const alert = alerts.find((row) => sameRule(row.rule, past.input));
    if (on && !alert) await repository.addSearchAlert(past.input);
    if (!on && alert) await repository.deleteSearchAlert(alert.id);
  });
}

/** Re-scores the jobs on the Tracker or on Jobs, as `scope` says, that were scored against an older resume. */
export async function rescoreJobs(scope: RescoreScope): Promise<ActionResult> {
  return run(scope === "tracker" ? "/tracker" : "/jobs", async () => {
    if (scope !== "tracker" && scope !== "jobs") throw new Error("Pick the Tracker or Jobs to score.");
    await callAgent("/runs/rescore", { method: "POST", body: { scope } });
  });
}

/** Starts a run that adds companies to the directory, one careers page URL or company name per line. */
export async function importCompanies(formData: FormData): Promise<ActionResult> {
  return run("/companies", async () => {
    const entries = [...new Set(text(formData.get("entries")).split(/[\n,]/).map((entry) => entry.trim()).filter(Boolean))];
    if (entries.length === 0) throw new Error("Enter at least one company or careers page URL.");
    if (entries.length > MAX_COMPANY_IMPORT) throw new Error(`Import up to ${MAX_COMPANY_IMPORT} companies at a time.`);
    if (entries.some((entry) => entry.length > MAX_IMPORT_ENTRY_LENGTH)) {
      throw new Error(`Each entry must be under ${MAX_IMPORT_ENTRY_LENGTH} characters.`);
    }
    await callAgent("/runs/import", { method: "POST", body: { entries } });
  });
}

/** Sorts a job's requirements into covered, weak and missing against the primary resume, and saves it. */
export async function analyzeGaps(id: string): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    await callAgent(`/applications/${encodeURIComponent(id)}/gap-analysis`, { method: "POST" });
  });
}

/** Stops a queued or running search, re-score or import; jobs it already added stay. */
export async function stopRun(runId: string): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    await callAgent(`/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" });
  });
}

export async function saveTheme(theme: string): Promise<ActionResult> {
  return run([], async () => {
    if (!THEMES.includes(theme as ThemeRow)) throw new Error("Unknown theme.");
    const { repository } = await getSignedInSource();
    await repository.saveTheme(theme as ThemeRow);
  });
}

export type AddJobResult = ActionResult & { message?: string; needsDetails?: boolean };

/**
 * Adds a job the user applied to outside the app to Jobs, then starts scoring it against the primary resume. The
 * job stays added when scoring can't start, such as while a search runs. `needsDetails` says the agent couldn't read
 * the link and needs the job's title, company and description.
 */
export async function addOutsideJob(formData: FormData): Promise<AddJobResult> {
  let message = "Added to Jobs. Scoring started.";
  let needsDetails = false;
  const result = await run("/jobs", async () => {
    const url = text(formData.get("url"));
    if (!/^https?:\/\/\S+$/.test(url)) throw new Error("Enter the job's link, starting with https://.");
    const status = text(formData.get("status")) || "applied";
    if (!OUTSIDE_STATUSES.includes(status as (typeof OUTSIDE_STATUSES)[number])) throw new Error("Pick a status.");
    const body = {
      url,
      status,
      applied_on: text(formData.get("applied_on")) || null,
      title: text(formData.get("title")) || null,
      company: text(formData.get("company")) || null,
      description: text(formData.get("description")) || null,
    };
    try {
      await callAgent("/applications/outside", { method: "POST", body });
    } catch (error) {
      needsDetails = error instanceof AgentError && error.status === 422;
      throw error;
    }
    try {
      await callAgent("/runs/rescore", { method: "POST", body: { scope: "jobs" } });
    } catch (error) {
      unstable_rethrow(error);
      message = `Added to Jobs, but scoring didn't start: ${error instanceof Error ? error.message : "try Rescore later."}`;
    }
  });
  return result.ok ? { ...result, message } : { ...result, needsDetails };
}

/** Deletes the signed-in account through the agent; the caller then signs the browser out. */
export async function deleteAccount(): Promise<ActionResult> {
  return run([], async () => {
    await callAgent("/me", { method: "DELETE" });
  });
}

export async function addLesson(formData: FormData): Promise<ActionResult> {
  return run("/insights", async () => {
    const lesson = text(formData.get("lesson"));
    if (!lesson) throw new Error("Write a preference, such as \"No jobs that need a security clearance\".");
    if (lesson.length > MAX_LESSON_LENGTH) throw new Error(`Keep it under ${MAX_LESSON_LENGTH} characters.`);
    const { repository } = await getSignedInSource();
    await repository.addLesson(lesson);
  });
}

export async function deleteLesson(id: string): Promise<ActionResult> {
  return run("/insights", async () => {
    const { repository } = await getSignedInSource();
    await repository.deleteLesson(id);
  });
}

/** Learns the lessons again from the user's ratings and statuses now. */
export async function refreshLessons(): Promise<ActionResult> {
  return run("/insights", async () => {
    await callAgent("/me/lessons/refresh", { method: "POST" });
  });
}

export type JobTextResult = ActionResult & { text?: { title: string; company: string; description: string } };

/** The title, company and description a saved job shows, for editing them. */
export async function loadJobText(id: string): Promise<JobTextResult> {
  let jobText: JobTextResult["text"];
  const result = await run([], async () => {
    const { repository } = await getSignedInSource();
    jobText = await repository.getJobText(id);
  });
  return { ...result, text: jobText };
}

/** Saves the user's own title, company and description for a saved job; a field left blank goes back to the job's. */
export async function editJob(id: string, formData: FormData): Promise<ActionResult> {
  return run(["/jobs", "/tracker"], async () => {
    const { repository } = await getSignedInSource();
    await repository.editJob(id, {
      edited_title: text(formData.get("title")) || null,
      edited_company: text(formData.get("company")) || null,
      edited_description: text(formData.get("description")) || null,
    });
  });
}

/** Turns the signed-in user's daily match emails on or off; their marked searches stay marked either way. */
export async function saveDailyEmails(on: boolean): Promise<ActionResult> {
  return run([], async () => {
    const { repository } = await getSignedInSource();
    await repository.saveDailyEmails(on === true);
  });
}

/** A search the daily email dialog lists, as `describeSearch` words it, and whether it runs each morning. */
export interface DailySearch {
  runId: string | null;
  alertId: string | null;
  title: string;
  detail: string;
  on: boolean;
}

export type DailySearchesResult = ActionResult & { searches?: DailySearch[] };

/** The user's last DAILY_SEARCH_CHOICES different searches, then any marked search older than those. */
export async function listDailySearches(): Promise<DailySearchesResult> {
  let searches: DailySearch[] = [];
  const result = await run([], async () => {
    const { repository } = await getSignedInSource();
    const [runs, alerts] = await Promise.all([repository.listRuns(DAILY_SEARCH_SCAN, "search"), repository.listSearchAlerts()]);
    const recent: AgentRunRow[] = [];
    for (const past of runs) {
      if (recent.length === DAILY_SEARCH_CHOICES) break;
      if (!recent.some((seen) => sameRule(seen.input, past.input))) recent.push(past);
    }
    const older = alerts.filter((alert) => !recent.some((past) => sameRule(past.input, alert.rule)));
    searches = [
      ...recent.map((past) => {
        const alert = alerts.find((row) => sameRule(row.rule, past.input));
        return { runId: past.id, alertId: alert?.id ?? null, on: !!alert, ...describeSearch(past.input as Partial<SearchRuleInput>) };
      }),
      ...older.map((alert) => ({ runId: null, alertId: alert.id, on: true, ...describeSearch(alert.rule as Partial<SearchRuleInput>) })),
    ];
  });
  return { ...result, searches };
}
