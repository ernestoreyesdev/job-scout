import type { SupabaseClient } from "@supabase/supabase-js";

import type {
  AgentRunRow,
  ApplicationRow,
  ApplicationStatusRow,
  CompanyRow,
  Database,
  PostingRow,
  ProfileRow,
  ResumeRow,
} from "./schema";

export type JobFinderClient = SupabaseClient<Database>;

export type TrackedJob = ApplicationRow & { posting: PostingRow };

export type DirectoryCompany = CompanyRow & { hidden: boolean };

export type ApplicationPatch = { status?: ApplicationStatusRow; notes?: string | null };

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
  async listTrackedJobs(view: "tracker" | "jobs", scoreAscending = false): Promise<TrackedJob[]> {
    const query = this.client.from("applications").select("*, posting:postings(*)");
    const { data, error } = await (view === "tracker" ? query.eq("in_tracker", true) : query.neq("status", "new")).order(
      "fit_score",
      { ascending: scoreAscending, nullsFirst: false },
    );
    if (error) throw error;
    return data;
  }

  async updateApplication(id: string, patch: ApplicationPatch): Promise<void> {
    const { error } = await this.client.from("applications").update(patch).eq("id", id);
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
  async listCompanies(): Promise<DirectoryCompany[]> {
    const [companies, hidden] = await Promise.all([
      this.client.from("companies").select("*").order("open_jobs", { ascending: false }),
      this.client.from("hidden_companies").select("company_id"),
    ]);
    if (companies.error) throw companies.error;
    if (hidden.error) throw hidden.error;
    const hiddenIds = new Set(hidden.data.map((row) => row.company_id));
    return companies.data.map((company) => ({ ...company, hidden: hiddenIds.has(company.id) }));
  }

  async setCompanyHidden(companyId: string, hidden: boolean): Promise<void> {
    if (hidden) {
      const { error } = await this.client
        .from("hidden_companies")
        .upsert({ user_id: await this.userId(), company_id: companyId });
      if (error) throw error;
      return;
    }
    const { error } = await this.client.from("hidden_companies").delete().eq("company_id", companyId);
    if (error) throw error;
  }
}
