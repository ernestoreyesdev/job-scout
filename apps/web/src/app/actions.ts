"use server";

import { revalidatePath } from "next/cache";
import { unstable_rethrow } from "next/navigation";

import {
  APPLICATION_STATUSES,
  MAX_JOBS_PER_SEARCH,
  WORKPLACE_TYPES,
  type ApplicationStatusRow,
  type SearchRuleInput,
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

export async function saveAnthropicKey(formData: FormData): Promise<ActionResult> {
  return run("/settings", async () => {
    const apiKey = text(formData.get("apiKey"));
    if (!apiKey) throw new Error("Paste your Anthropic API key.");
    await callAgent("/me/anthropic-key", { method: "PUT", body: { api_key: apiKey } });
  });
}

export async function removeAnthropicKey(): Promise<ActionResult> {
  return run("/settings", async () => {
    await callAgent("/me/anthropic-key", { method: "DELETE" });
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

    const rule: SearchRuleInput = {
      keywords,
      company,
      workplace_types: workplaceTypes as WorkplaceTypeRow[],
      location,
      limit,
    };
    await callAgent("/runs/search", { method: "POST", body: rule });
  });
}

export async function updateApplication(id: string, formData: FormData): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    const status = formData.get("status");
    const notes = formData.get("notes");
    if (status !== null && !APPLICATION_STATUSES.includes(status as ApplicationStatusRow)) {
      throw new Error("Unknown status.");
    }

    const { repository } = await getSignedInSource();
    await repository.updateApplication(id, {
      ...(status !== null && { status: status as ApplicationStatusRow }),
      ...(notes !== null && { notes: text(notes) || null }),
    });
  });
}

/** Starts a new run with the same rule as a failed one. */
export async function rerunSearch(runId: string): Promise<ActionResult> {
  return run("/tracker", async () => {
    const { repository } = await getSignedInSource();
    const previous = await repository.getRun(runId);
    if (!previous) throw new Error("Search not found.");
    if (previous.status !== "failed") throw new Error("Only failed searches can be re-run.");

    const input = previous.input as Partial<SearchRuleInput>;
    if (!input.keywords?.length) throw new Error("This search has no keywords. Start a new one instead.");

    const rule: SearchRuleInput = {
      keywords: input.keywords,
      company: input.company ?? null,
      workplace_types: input.workplace_types ?? [],
      location: input.location ?? null,
      limit: input.limit ?? 10,
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

/** Takes a job off the Tracker; it stays under Jobs. */
export async function removeFromTracker(id: string): Promise<ActionResult> {
  return run(["/tracker", "/jobs"], async () => {
    const { repository } = await getSignedInSource();
    await repository.removeFromTracker(id);
  });
}

/** Empties the Tracker; jobs past "new" stay under Jobs. */
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
