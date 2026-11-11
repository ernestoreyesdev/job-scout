"use server";

import { revalidatePath } from "next/cache";
import { unstable_rethrow } from "next/navigation";

import {
  APPLICATION_STATUSES,
  FIT_LABELS,
  MAX_COMPANY_IMPORT,
  MAX_JOBS_PER_SEARCH,
  MIN_SCORES,
  POSTED_WITHIN_DAYS,
  THEMES,
  WORKPLACE_TYPES,
  type ApplicationStatusRow,
  type FitLabelRow,
  type SearchRuleInput,
  type ThemeRow,
  type WorkplaceTypeRow,
} from "@/lib/db";
import { callAgent } from "@/lib/agent";
import { getSignedInSource } from "@/lib/repository";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

const MAX_RESUME_BYTES = 1024 * 1024;

/** Runs an action, turning thrown validation, database or agent errors into a result. */
async function run(paths: string | string[], work: () => Promise<void>): Promise<ActionResult> {
  try {
    await work();
    for (const path of [paths].flat()) revalidatePath(path);
    return { ok: true };
  } catch (error) {
    // Lets a sign-in redirect through instead of reporting it as a failure.
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
    if (!/\.(pdf|docx)$/i.test(file.name)) throw new Error("Only PDF and .docx resumes are supported.");
    if (file.size > MAX_RESUME_BYTES) throw new Error("Resumes must be under 1 MB.");

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
    if (company && company.length > 100) throw new Error("Company names must be under 100 characters.");

    const workplaceTypes = formData.getAll("workplace").map(String);
    if (!workplaceTypes.every((type) => WORKPLACE_TYPES.includes(type as WorkplaceTypeRow))) {
      throw new Error("Unknown location type.");
    }

    const location = text(formData.get("location")) || null;
    if (location && location.length > 100) throw new Error("Locations must be under 100 characters.");

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

    const rule: SearchRuleInput = {
      keywords: input.keywords,
      company: input.company ?? null,
      workplace_types: input.workplace_types ?? [],
      location: input.location ?? null,
      limit: input.limit ?? 10,
      web_lookup: webLookup || (input.web_lookup ?? false),
      exclude: input.exclude ?? [],
      posted_within_days: input.posted_within_days ?? null,
      score: input.score ?? true,
      min_score: input.min_score ?? null,
    };
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

/** Re-scores the Tracker and Jobs entries scored against an older resume. */
export async function rescoreJobs(): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    await callAgent("/runs/rescore", { method: "POST" });
  });
}

/** Starts a run that adds companies to the directory, one careers page URL or company name per line. */
export async function importCompanies(formData: FormData): Promise<ActionResult> {
  return run("/companies", async () => {
    const entries = [...new Set(text(formData.get("entries")).split(/[\n,]/).map((entry) => entry.trim()).filter(Boolean))];
    if (entries.length === 0) throw new Error("Enter at least one company or careers page URL.");
    if (entries.length > MAX_COMPANY_IMPORT) throw new Error(`Import up to ${MAX_COMPANY_IMPORT} companies at a time.`);
    if (entries.some((entry) => entry.length > 300)) throw new Error("Each entry must be under 300 characters.");
    await callAgent("/runs/import", { method: "POST", body: { entries } });
  });
}

/** Sorts a job's requirements into covered, weak and missing against the primary resume, and saves it. */
export async function analyzeGaps(id: string): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    await callAgent(`/applications/${encodeURIComponent(id)}/gap-analysis`, { method: "POST" });
  });
}

export type FollowUpResult = ActionResult & { subject?: string; body?: string };

/** Drafts a follow-up email for an application with no response; nothing is sent. */
export async function draftFollowUp(id: string): Promise<FollowUpResult> {
  try {
    const draft = await callAgent<{ subject: string; body: string }>(
      `/applications/${encodeURIComponent(id)}/follow-up`,
      { method: "POST" },
    );
    return { ok: true, subject: draft.subject, body: draft.body };
  } catch (error) {
    unstable_rethrow(error);
    return { ok: false, error: error instanceof Error ? error.message : "Could not draft a follow-up." };
  }
}

/** Stops a queued or running search, re-score or import; jobs it already added stay. */
export async function stopRun(runId: string): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    await callAgent(`/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" });
  });
}

export async function saveTheme(theme: string): Promise<ActionResult> {
  return run("/settings", async () => {
    if (!THEMES.includes(theme as ThemeRow)) throw new Error("Unknown theme.");
    const { repository } = await getSignedInSource();
    await repository.saveTheme(theme as ThemeRow);
  });
}
