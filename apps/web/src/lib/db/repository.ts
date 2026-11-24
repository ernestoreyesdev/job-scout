import type { PostgrestError, SupabaseClient } from "@supabase/supabase-js";

import type {
  AgentRunRow,
  ApplicationEventRow,
  ApplicationRow,
  ApplicationStatusRow,
  CompanyRow,
  CompanySort,
  Database,
  FitLabelRow,
  JobSort,
  LessonRow,
  PostingRow,
  RescoreScope,
  ResumeRow,
  ThemeRow,
} from "./schema";
import { GHOST_JOB_DAYS, LESSON_FADE_DAYS, REPOST_DAYS, SKIPPED_COMPANY_KINDS } from "./schema";
import type { FunnelJob, ScoredJob } from "../insights";
import { jobKey } from "../job-key";

export type JobFinderClient = SupabaseClient<Database>;

type TrackedJobRow = ApplicationRow & {
  posting: Omit<PostingRow, "description" | "description_hash">;
  events: Pick<ApplicationEventRow, "status" | "changed_at">[];
};

/**
 * Signals that depend on today's date: days since the posting went up (while it's listed), whether the same
 * company listed the same title before under another posting, and days since the job was marked applied.
 */
export type JobSignals = {
  openDays: number | null;
  reposted: boolean;
  duplicateOf: ApplicationStatusRow | null;
};

export type TrackedJob = TrackedJobRow & { signals: JobSignals };

const DAY_MS = 24 * 60 * 60 * 1000;

/** Narrows the Tracker or Jobs list; every field is optional. */
export type JobFilters = {
  status?: ApplicationStatusRow;
  company?: string;
  hideClosed?: boolean;
  hideClearance?: boolean;
  minSalary?: number;
};

/** Which jobs a list shows: the Tracker's, Jobs' default (saved and beyond) or Jobs' rated view. */
export type JobView = "tracker" | "jobs" | "rated";

export type DirectoryCompany = CompanyRow & { hidden: boolean };

export type ApplicationPatch = { status?: ApplicationStatusRow; notes?: string | null; fit_label?: FitLabelRow | null };

export type JobEdits = Pick<ApplicationRow, "edited_title" | "edited_company" | "edited_description">;

/** One page of a list: its rows, the page number shown and how many pages there are. */
export type Page<T> = { items: T[]; page: number; pageCount: number; total: number };

export const PAGE_SIZE = 10;

export const COMPANIES_PAGE_SIZE = 15;

type PageResult<T> = { data: T[] | null; error: PostgrestError | null; count: number | null };

const RESUME_BUCKET = "resumes";

/**
 * Reads and writes through Supabase. Row-level security scopes every query to
 * the signed-in user; userId only fills owner columns and storage paths, which RLS checks.
 */
export class JobFinderRepository {
  constructor(
    private readonly client: JobFinderClient,
    private readonly userId: string,
  ) {}

  async getPrimaryResume(): Promise<ResumeRow | null> {
    const { data, error } = await this.client
      .from("resumes")
      .select("*")
      .eq("is_primary", true)
      .maybeSingle();
    if (error) throw error;
    return data;
  }

  /** Stores the file as a new object and makes it the primary resume. */
  async uploadResume(file: File): Promise<ResumeRow> {
    const userId = this.userId;
    const storagePath = `${userId}/${crypto.randomUUID()}-${file.name}`;

    const upload = await this.client.storage.from(RESUME_BUCKET).upload(storagePath, file, {
      contentType: file.type || undefined,
    });
    if (upload.error) throw upload.error;

    const demote = await this.client
      .from("resumes")
      .update({ is_primary: false })
      .eq("is_primary", true);
    if (demote.error) throw demote.error;

    const { data, error } = await this.client
      .from("resumes")
      .insert({ user_id: userId, storage_path: storagePath, file_name: file.name, is_primary: true })
      .select()
      .single();
    if (error) throw error;
    return data;
  }

  /** "tracker" lists jobs still on the Tracker, "jobs" every job moved past new, "rated" every job marked good or bad. */
  async listTrackedJobs(
    view: JobView,
    sort: JobSort = "desc",
    page = 1,
    filters: JobFilters = {},
  ): Promise<Page<TrackedJob>> {
    const atCompany = filters.company ? await this.idsAtCompany(filters.company) : null;
    const result = await this.paged<TrackedJobRow>(page, (from, to) => {
      let query = this.client
        .from("applications")
        .select(
          "*, posting:postings!inner(id, source, board, external_id, title, company, location, url, posted_at, workplace_type, closed_at, salary_min, salary_max, salary_currency, salary_period, clearance, visa_sponsorship, years_experience, tech_stack, details_extracted_at, created_at, updated_at), events:application_events(status, changed_at)",
          { count: "exact" },
        );
      query = inView(query, view);
      if (filters.status) query = query.eq("status", filters.status);
      if (atCompany) query = query.in("id", atCompany);
      if (filters.hideClosed) query = query.is("posting.closed_at", null);
      if (filters.hideClearance) {
        query = query.or("details_extracted_at.is.null,clearance.is.null", { referencedTable: "posting" });
      }
      if (filters.minSalary) {
        query = query.or(
          `details_extracted_at.is.null,and(salary_period.eq.year,salary_max.gte.${filters.minSalary})`,
          { referencedTable: "posting" },
        );
      }
      const ordered =
        sort === "posted"
          ? query.order("posting(posted_at)", { ascending: false, nullsFirst: false })
          : sort === "added"
            ? query.order("created_at", { ascending: false })
            : sort === "status"
              ? query.order("status", { ascending: false }).order("fit_score", { ascending: false, nullsFirst: false })
              : query.order("fit_score", { ascending: sort === "asc", nullsFirst: false });
      return ordered.order("id").order("changed_at", { referencedTable: "events" }).range(from, to);
    });
    const items = result.items.map((job) => ({
      ...job,
      posting: { ...job.posting, title: job.edited_title ?? job.posting.title, company: job.edited_company ?? job.posting.company },
    }));
    return { ...result, items: await this.withSignals(items) };
  }

  /**
   * Adds each job's signals: its dates, whether the database says it's a repost, as `reposted_postings` defines it,
   * and the status of another job the user tracks with the same company and title, as `jobKey` compares them.
   */
  private async withSignals(jobs: TrackedJobRow[]): Promise<TrackedJob[]> {
    if (!jobs.length) return [];
    const [{ data: reposts, error }, { data: tracked, error: trackedError }] = await Promise.all([
      this.client.rpc("reposted_postings", { job_ids: jobs.map((job) => job.posting.id), days: REPOST_DAYS }),
      this.client.from("applications").select("id, status, edited_title, edited_company, posting:postings!inner(company, title)"),
    ]);
    if (error) throw error;
    if (trackedError) throw trackedError;
    const reposted = new Set(reposts.map((row) => row.id));
    const copies = new Map<string, { id: string; status: ApplicationStatusRow }[]>();
    for (const row of tracked) {
      const key = jobKey(row.edited_company ?? row.posting.company, row.edited_title ?? row.posting.title);
      copies.set(key, [...(copies.get(key) ?? []), { id: row.id, status: row.status }]);
    }
    const now = Date.now();
    const days = (date: string) => daysSince(date, now);
    return jobs.map((job) => {
      return {
        ...job,
        signals: {
          openDays: job.posting.closed_at ? null : days(job.posting.posted_at ?? job.posting.created_at),
          reposted: reposted.has(job.posting.id),
          duplicateOf:
            copies.get(jobKey(job.posting.company, job.posting.title))?.find((copy) => copy.id !== job.id)?.status ?? null,
        },
      };
    });
  }

  /**
   * The Tracker holds only new, unrated jobs: moving a job past new or rating it takes it off, setting it back to new
   * or clearing the rating of a new job returns it. Rating a new job good also saves it.
   */
  async updateApplication(id: string, patch: ApplicationPatch): Promise<void> {
    const update = {
      ...patch,
      ...(patch.status !== undefined && { in_tracker: patch.status === "new" }),
      ...(patch.fit_label && { in_tracker: false }),
    };
    const { error } = await this.client.from("applications").update(update).eq("id", id);
    if (error) throw error;
    if (patch.fit_label === "good") {
      const saved = await this.client.from("applications").update({ status: "saved" }).eq("id", id).eq("status", "new");
      if (saved.error) throw saved.error;
    }
    if (patch.fit_label === null) {
      const returned = await this.client.from("applications").update({ in_tracker: true }).eq("id", id).eq("status", "new");
      if (returned.error) throw returned.error;
    }
  }

  async listRuns(limit = 5, kind?: string): Promise<AgentRunRow[]> {
    let query = this.client
      .from("agent_runs")
      .select(
        "id, user_id, kind, input, status, error, error_code, progress, usage, timings, jobs_added, created_at, updated_at, finished_at",
      );
    if (kind) query = query.eq("kind", kind);
    const { data, error } = await query.order("created_at", { ascending: false }).limit(limit);
    if (error) throw error;
    return data;
  }

  async getRun(id: string): Promise<AgentRunRow | null> {
    const { data, error } = await this.client.from("agent_runs").select("*").eq("id", id).maybeSingle();
    if (error) throw error;
    return data;
  }

  async deleteApplication(id: string): Promise<void> {
    const { error } = await this.client.from("applications").delete().eq("id", id);
    if (error) throw error;
  }

  /** Empties the Tracker: unrated new jobs are deleted, rated ones leave it and stay under Jobs' rated view. */
  async clearTracker(): Promise<void> {
    const removed = await this.client
      .from("applications")
      .delete()
      .eq("in_tracker", true)
      .eq("status", "new")
      .is("fit_label", null);
    if (removed.error) throw removed.error;

    const hidden = await this.client.from("applications").update({ in_tracker: false }).eq("in_tracker", true);
    if (hidden.error) throw hidden.error;
  }

  /** The shared directory, most open jobs first, flagged with whether this user hid each company. */
  async listCompanies(
    page = 1,
    search = "",
    sort: CompanySort = "jobs",
    ascending = false,
  ): Promise<Page<DirectoryCompany>> {
    const column = { name: "name", jobs: "open_jobs", checked: "checked_at" } as const satisfies Record<CompanySort, string>;
    const [companies, hidden] = await Promise.all([
      this.paged(
        page,
        (from, to) => {
          const query = this.client.from("companies").select("*", { count: "exact" });
          return (search ? query.ilike("name", `%${search.replace(/[\\%_]/g, "\\$&")}%`) : query)
            .order(column[sort], { ascending })
            .order("id")
            .range(from, to);
        },
        COMPANIES_PAGE_SIZE,
      ),
      this.client.from("hidden_companies").select("company_id, hidden"),
    ]);
    if (hidden.error) throw hidden.error;
    const choices = new Map(hidden.data.map((row) => [row.company_id, row.hidden]));
    return {
      ...companies,
      items: companies.items.map((company) => ({
        ...company,
        hidden: (company.kind !== null && SKIPPED_COMPANY_KINDS.includes(company.kind)) || (choices.get(company.id) ?? false),
      })),
    };
  }

  /** Records the user's choice to hide a company from searches or show it again. */
  async setCompanyHidden(companyId: string, hidden: boolean): Promise<void> {
    const { error } = await this.client
      .from("hidden_companies")
      .upsert({ user_id: this.userId, company_id: companyId, hidden });
    if (error) throw error;
  }

  /**
   * Loads one page of `size` rows with the total count. A page past the end
   * (the last row of the last page was just deleted) falls back to the last page.
   */
  private async paged<T>(
    page: number,
    load: (from: number, to: number) => PromiseLike<PageResult<T>>,
    size = PAGE_SIZE,
  ): Promise<Page<T>> {
    const fetchPage = (n: number) => load((n - 1) * size, n * size - 1);
    let current = Math.max(1, Math.floor(page));
    let result = await fetchPage(current);
    if (result.error?.code === "PGRST103" && current > 1) {
      const first = await fetchPage(1);
      if (first.error) throw first.error;
      current = Math.max(1, Math.ceil((first.count ?? 0) / size));
      result = current === 1 ? first : await fetchPage(current);
    }
    if (result.error) throw result.error;
    const total = result.count ?? 0;
    return { items: result.data ?? [], page: current, pageCount: Math.max(1, Math.ceil(total / size)), total };
  }

  /** Jobs on the Tracker or on Jobs, as `scope` says, that were scored against a resume other than `resumeId`. */
  async countStaleJobs(resumeId: string, scope: RescoreScope): Promise<number> {
    const query = this.client
      .from("applications")
      .select("id", { count: "exact", head: true })
      .or(`resume_id.is.null,resume_id.neq.${resumeId}`);
    const { count, error } = await inView(query, scope);
    if (error) throw error;
    return count ?? 0;
  }

  /** Companies of the jobs in a view, for its company filter. */
  async listTrackedCompanies(view: JobView): Promise<string[]> {
    const query = this.client.from("applications").select("edited_company, posting:postings!inner(company)");
    const { data, error } = await inView(query, view);
    if (error) throw error;
    return [...new Set(data.map((row) => row.edited_company ?? row.posting.company))].sort((a, b) => a.localeCompare(b));
  }

  /** Every job on the Tracker, whatever the filters, since Clear empties all of them. */
  async countTrackerJobs(): Promise<number> {
    const { count, error } = await this.client
      .from("applications")
      .select("id", { count: "exact", head: true })
      .eq("in_tracker", true);
    if (error) throw error;
    return count ?? 0;
  }

  /** Every job scored for the user with its score, thumbs, status and source, for Insights. */
  async listScoredJobs(): Promise<ScoredJob[]> {
    const { data, error } = await this.client
      .from("applications")
      .select("fit_score, fit_label, status, posting:postings!inner(source)")
      .not("fit_score", "is", null)
      .range(0, 9999);
    if (error) throw error;
    return data.map(({ posting, ...job }) => ({ ...job, source: posting.source }));
  }

  /** Jobs past "new" with their status history, source, scoring resume's file name and who added them, for the funnel. */
  async listFunnelJobs(): Promise<FunnelJob[]> {
    const { data, error } = await this.client
      .from("applications")
      .select("status, added_by, posting:postings!inner(source), resume:resumes(file_name), events:application_events(status)")
      .neq("status", "new")
      .range(0, 9999);
    if (error) throw error;
    return data.map((job) => ({
      statuses: [job.status, ...job.events.map((event) => event.status)],
      source: job.posting.source,
      resume: job.resume?.file_name ?? "Unknown resume",
      addedBy: job.added_by,
    }));
  }

  /** The user's tracked jobs whose posting is still listed GHOST_JOB_DAYS or more after it went up. */
  async countAgingJobs(): Promise<number> {
    const { data, error } = await this.client
      .from("applications")
      .select("posting:postings!inner(posted_at, created_at, closed_at)")
      .or("in_tracker.eq.true,status.neq.new")
      .is("posting.closed_at", null)
      .range(0, 9999);
    if (error) throw error;
    const cutoff = Date.now() - GHOST_JOB_DAYS * DAY_MS;
    return data.filter((job) => new Date(job.posting.posted_at ?? job.posting.created_at).getTime() <= cutoff).length;
  }

  /** Saves the user's color theme, creating their profile row if it doesn't exist yet. */
  async saveTheme(theme: ThemeRow): Promise<void> {
    const { error } = await this.client.from("profiles").upsert({ user_id: this.userId, theme });
    if (error) throw error;
  }

  /** Everything the admin page shows, from the admin_stats database function; it refuses anyone but an admin. */
  async getAdminStats<T>(): Promise<T> {
    const { data, error } = await this.client.rpc("admin_stats");
    if (error) throw error;
    return data as T;
  }

  /** The user's own lessons and their learned ones confirmed within LESSON_FADE_DAYS, oldest first. */
  async listLessons(): Promise<LessonRow[]> {
    const cutoff = new Date(Date.now() - LESSON_FADE_DAYS * DAY_MS).toISOString();
    const { data, error } = await this.client
      .from("lessons")
      .select("*")
      .is("deleted_at", null)
      .or(`source.eq.user,confirmed_at.gt.${cutoff}`)
      .order("created_at");
    if (error) throw error;
    return data;
  }

  async addLesson(text: string): Promise<void> {
    const { error } = await this.client.from("lessons").insert({ user_id: this.userId, text, source: "user" });
    if (error) throw error;
  }

  /** Marks the lesson deleted, keeping its row so it isn't learned again. */
  async deleteLesson(id: string): Promise<void> {
    const { error } = await this.client.from("lessons").update({ deleted_at: new Date().toISOString() }).eq("id", id);
    if (error) throw error;
  }

  /** The space saved jobs take and how many open jobs have no embedding; it refuses anyone but an admin. */
  async getAdminStorage(): Promise<{ bytes: number; unembedded: number }> {
    const { data, error } = await this.client.rpc("admin_storage");
    if (error) throw error;
    return data;
  }

  /** The user's saved jobs at a company, by their own company name for the job when they set one, else the job's. */
  private async idsAtCompany(company: string): Promise<string[]> {
    const [edited, original] = await Promise.all([
      this.client.from("applications").select("id").eq("edited_company", company),
      this.client.from("applications").select("id, posting:postings!inner(company)").is("edited_company", null).eq("posting.company", company),
    ]);
    if (edited.error) throw edited.error;
    if (original.error) throw original.error;
    return [...edited.data, ...original.data].map((row) => row.id);
  }

  /** The title, company and description a saved job shows: the user's own where they set them, else the job's. */
  async getJobText(id: string): Promise<{ title: string; company: string; description: string }> {
    const { data, error } = await this.client
      .from("applications")
      .select("edited_title, edited_company, edited_description, posting:postings!inner(title, company, description)")
      .eq("id", id)
      .single();
    if (error) throw error;
    return {
      title: data.edited_title ?? data.posting.title,
      company: data.edited_company ?? data.posting.company,
      description: data.edited_description ?? data.posting.description,
    };
  }

  /** Saves the user's corrections; the job's score and gap analysis become out of date until it is scored again. */
  async editJob(id: string, edits: JobEdits): Promise<void> {
    const { error } = await this.client
      .from("applications")
      .update({ ...edits, resume_id: null, gap_analysis: null, gap_analyzed_at: null })
      .eq("id", id);
    if (error) throw error;
  }
}

interface ViewFilter {
  eq(column: string, value: unknown): this;
  neq(column: string, value: unknown): this;
  not(column: string, operator: string, value: unknown): this;
}

/** Narrows an applications query to a view's jobs: the Tracker, rated jobs, or every job past "new" on Jobs. */
function inView<Q extends ViewFilter>(query: Q, view: JobView): Q {
  if (view === "tracker") return query.eq("in_tracker", true);
  if (view === "rated") return query.not("fit_label", "is", null);
  return query.neq("status", "new");
}

function daysSince(date: string, now: number): number {
  return Math.floor((now - new Date(date).getTime()) / DAY_MS);
}
