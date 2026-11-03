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
  PostingRow,
  ProfileRow,
  ResumeRow,
} from "./schema";
import { FOLLOW_UP_DAYS, GHOST_JOB_DAYS, SKIPPED_COMPANY_KINDS } from "./schema";
import type { FunnelJob, ScoredJob } from "../insights";

export type JobFinderClient = SupabaseClient<Database>;

type TrackedJobRow = ApplicationRow & {
  posting: PostingRow;
  events: Pick<ApplicationEventRow, "status" | "changed_at">[];
};

/**
 * Signals that depend on today's date: days since the posting went up (while it's listed), whether the same
 * company listed the same title before under another posting, and days since the job was marked applied.
 */
export type JobSignals = { openDays: number | null; reposted: boolean; daysSinceApplied: number | null };

export type TrackedJob = TrackedJobRow & { signals: JobSignals };

const DAY_MS = 24 * 60 * 60 * 1000;

function sameTitle(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/** Narrows the Tracker or Jobs list; every field is optional. */
export type JobFilters = {
  status?: ApplicationStatusRow;
  company?: string;
  hideClosed?: boolean;
  hideClearance?: boolean;
  minSalary?: number;
};

export type DirectoryCompany = CompanyRow & { hidden: boolean };

export type ApplicationPatch = { status?: ApplicationStatusRow; notes?: string | null; fit_label?: FitLabelRow | null };

/** One page of a list: its rows, the page number shown and how many pages there are. */
export type Page<T> = { items: T[]; page: number; pageCount: number; total: number };

export const PAGE_SIZE = 10;

export const COMPANIES_PAGE_SIZE = 15;

type PageResult<T> = { data: T[] | null; error: PostgrestError | null; count: number | null };

const RESUME_BUCKET = "resumes";

/**
 * Reads and writes through Supabase. Row-level security scopes every query to
 * the signed-in user, so no user id is passed in here.
 */
export class JobFinderRepository {
  constructor(private readonly client: JobFinderClient) {}

  /** Inserts and storage paths need the owner explicitly; RLS then checks it matches the caller. */
  private async userId(): Promise<string> {
    const {
      data: { user },
    } = await this.client.auth.getUser();
    if (!user) throw new Error("Not signed in.");
    return user.id;
  }

  async getProfile(): Promise<ProfileRow | null> {
    const { data, error } = await this.client.from("profiles").select("*").maybeSingle();
    if (error) throw error;
    return data;
  }

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
    const userId = await this.userId();
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

  /** "tracker" lists jobs not removed from the Tracker; "jobs" lists every job the user has moved past new. */
  async listTrackedJobs(
    view: "tracker" | "jobs",
    sort: JobSort = "desc",
    page = 1,
    filters: JobFilters = {},
  ): Promise<Page<TrackedJob>> {
    const result = await this.paged<TrackedJobRow>(page, (from, to) => {
      let query = this.client
        .from("applications")
        .select("*, posting:postings!inner(*), events:application_events(status, changed_at)", { count: "exact" });
      query = view === "tracker" ? query.eq("in_tracker", true) : query.neq("status", "new");
      if (filters.status) query = query.eq("status", filters.status);
      if (filters.company) query = query.eq("posting.company", filters.company);
      if (filters.hideClosed) query = query.is("posting.closed_at", null);
      if (filters.hideClearance) query = query.is("posting.clearance", null);
      if (filters.minSalary) {
        query = query.eq("posting.salary_period", "year").gte("posting.salary_max", filters.minSalary);
      }
      const ordered =
        sort === "posted"
          ? query.order("posting(posted_at)", { ascending: false, nullsFirst: false })
          : sort === "added"
            ? query.order("created_at", { ascending: false })
            : query.order("fit_score", { ascending: sort === "asc", nullsFirst: false });
      return ordered.order("id").order("changed_at", { referencedTable: "events" }).range(from, to);
    });
    return { ...result, items: await this.withSignals(result.items) };
  }

  /** Adds each job's date-based signals; reposts are found among other postings from the same companies. */
  private async withSignals(jobs: TrackedJobRow[]): Promise<TrackedJob[]> {
    const companies = [...new Set(jobs.map((job) => job.posting.company))];
    const { data: others, error } = companies.length
      ? await this.client.from("postings").select("id, company, title, created_at").in("company", companies)
      : { data: [], error: null };
    if (error) throw error;
    const now = Date.now();
    const days = (date: string) => Math.floor((now - new Date(date).getTime()) / DAY_MS);
    return jobs.map((job) => {
      const applied = job.events.filter((event) => event.status === "applied").at(-1);
      return {
        ...job,
        signals: {
          openDays: job.posting.closed_at ? null : days(job.posting.posted_at ?? job.posting.created_at),
          reposted: others.some(
            (other) =>
              other.id !== job.posting.id &&
              other.company === job.posting.company &&
              sameTitle(other.title) === sameTitle(job.posting.title) &&
              other.created_at < job.posting.created_at,
          ),
          daysSinceApplied: job.status === "applied" && applied ? days(applied.changed_at) : null,
        },
      };
    });
  }

  /** Setting a job back to "new" also returns it to the Tracker, since Jobs only lists jobs past new. */
  async updateApplication(id: string, patch: ApplicationPatch): Promise<void> {
    const update = patch.status === "new" ? { ...patch, in_tracker: true } : patch;
    const { error } = await this.client.from("applications").update(update).eq("id", id);
    if (error) throw error;
  }

  async listRuns(limit = 5): Promise<AgentRunRow[]> {
    const { data, error } = await this.client
      .from("agent_runs")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(limit);
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

  /** Only jobs past "new" can leave the Tracker, since those are the ones Jobs still lists. */
  async removeFromTracker(id: string): Promise<void> {
    const { data, error } = await this.client
      .from("applications")
      .update({ in_tracker: false })
      .eq("id", id)
      .neq("status", "new")
      .select("id");
    if (error) throw error;
    if (data.length === 0) throw new Error("Save the job first, or delete it.");
  }

  /** Empties the Tracker: new jobs are deleted, the rest leave the Tracker and stay under Jobs. */
  async clearTracker(): Promise<void> {
    const removed = await this.client.from("applications").delete().eq("in_tracker", true).eq("status", "new");
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
        hidden: choices.get(company.id) ?? (company.kind !== null && SKIPPED_COMPANY_KINDS.includes(company.kind)),
      })),
    };
  }

  /** Records the user's choice, which overrides the default of hiding staffing agencies and aggregators. */
  async setCompanyHidden(companyId: string, hidden: boolean): Promise<void> {
    const { error } = await this.client
      .from("hidden_companies")
      .upsert({ user_id: await this.userId(), company_id: companyId, hidden });
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

  /** Jobs on the Tracker or Jobs that were scored against a resume other than `resumeId`. */
  async countStaleJobs(resumeId: string): Promise<number> {
    const { count, error } = await this.client
      .from("applications")
      .select("id", { count: "exact", head: true })
      .or(`resume_id.is.null,resume_id.neq.${resumeId}`)
      .or("in_tracker.eq.true,status.neq.new");
    if (error) throw error;
    return count ?? 0;
  }

  /** Companies of the jobs in a view, for its company filter. */
  async listTrackedCompanies(view: "tracker" | "jobs"): Promise<string[]> {
    const query = this.client.from("applications").select("posting:postings!inner(company)");
    const { data, error } = await (view === "tracker" ? query.eq("in_tracker", true) : query.neq("status", "new"));
    if (error) throw error;
    return [...new Set(data.map((row) => row.posting.company))].sort((a, b) => a.localeCompare(b));
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

  /** The user's runs from the last `days` days, newest first. */
  async listRecentRuns(days: number): Promise<AgentRunRow[]> {
    const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
    const { data, error } = await this.client
      .from("agent_runs")
      .select("*")
      .gte("created_at", since.toISOString())
      .order("created_at", { ascending: false });
    if (error) throw error;
    return data;
  }

  /** Jobs past "new" with their status history, source and scoring resume's file name, for the funnel. */
  async listFunnelJobs(): Promise<FunnelJob[]> {
    const { data, error } = await this.client
      .from("applications")
      .select("status, posting:postings!inner(source), resume:resumes(file_name), events:application_events(status)")
      .neq("status", "new")
      .range(0, 9999);
    if (error) throw error;
    return data.map((job) => ({
      statuses: [job.status, ...job.events.map((event) => event.status)],
      source: job.posting.source,
      resume: job.resume?.file_name ?? "Unknown resume",
    }));
  }

  /** Jobs still "applied" FOLLOW_UP_DAYS or more after being marked so, longest waiting first. */
  async listFollowUpsDue(): Promise<{ id: string; title: string; company: string; days: number }[]> {
    const { data, error } = await this.client
      .from("applications")
      .select("id, posting:postings!inner(title, company), events:application_events(status, changed_at)")
      .eq("status", "applied");
    if (error) throw error;
    const now = Date.now();
    return data
      .map((job) => {
        const applied = job.events.filter((event) => event.status === "applied").map((event) => event.changed_at).sort().at(-1);
        const days = applied ? Math.floor((now - new Date(applied).getTime()) / DAY_MS) : 0;
        return { id: job.id, title: job.posting.title, company: job.posting.company, days };
      })
      .filter((job) => job.days >= FOLLOW_UP_DAYS)
      .sort((a, b) => b.days - a.days);
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
}
