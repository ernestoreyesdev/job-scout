/**
 * Row shapes for the tables in `supabase/migrations`. Hand-written rather than
 * generated so the app builds without the Supabase CLI; keep in step with the
 * migrations.
 *
 * These must stay type aliases: supabase-js constrains them to
 * `Record<string, unknown>`, and an interface has no implicit index signature,
 * so declaring one here silently collapses every query result to `never`.
 */
export type JobSourceRow = "greenhouse" | "lever" | "ashby" | "smartrecruiters" | "workable" | "recruitee" | "workday";

export const APPLICATION_STATUSES = ["new", "saved", "tailored", "applied", "interviewing", "rejected"] as const;

export type ApplicationStatusRow = (typeof APPLICATION_STATUSES)[number];

export type RunStatusRow = "queued" | "running" | "done" | "failed";

export const WORKPLACE_TYPES = ["onsite", "hybrid", "remote"] as const;

export type WorkplaceTypeRow = (typeof WORKPLACE_TYPES)[number];

export type CompanyOriginRow = "lookup" | "discovery";

export type CompanyKindRow = "employer" | "staffing" | "aggregator";

/** Kinds a search skips unless the user chose to show the company. */
export const SKIPPED_COMPANY_KINDS: readonly CompanyKindRow[] = ["staffing", "aggregator"];

export const POSTED_WITHIN_DAYS = [1, 3, 7, 14, 30] as const;

/** Upper bound the agent accepts for jobs scored in one search. */
export const MAX_JOBS_PER_SEARCH = 25;

export type ProfileRow = {
  user_id: string;
  anthropic_key_hint: string | null;
  updated_at: string;
};

export type ResumeRow = {
  id: string;
  user_id: string;
  storage_path: string;
  file_name: string;
  text: string | null;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
};

export type PostingRow = {
  id: string;
  source: JobSourceRow;
  board: string;
  external_id: string;
  title: string;
  company: string;
  location: string | null;
  url: string;
  description: string;
  posted_at: string | null;
  workplace_type: WorkplaceTypeRow | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ApplicationRow = {
  id: string;
  user_id: string;
  posting_id: string;
  resume_id: string | null;
  fit_score: number | null;
  fit_summary: string | null;
  strengths: string[];
  gaps: string[];
  status: ApplicationStatusRow;
  notes: string | null;
  in_tracker: boolean;
  created_at: string;
  updated_at: string;
};

export type RunUsage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
  web_search_requests?: number;
};

export type CompanyRow = {
  id: string;
  name: string;
  source: JobSourceRow;
  board: string;
  open_jobs: number;
  found_by: CompanyOriginRow;
  checked_at: string;
  careers_url: string | null;
  kind: CompanyKindRow | null;
  created_at: string;
};

/** `agent_runs.input` for search runs. */
export type SearchRuleInput = {
  keywords: string[];
  company: string | null;
  workplace_types: WorkplaceTypeRow[];
  location: string | null;
  limit: number;
  web_lookup: boolean;
  exclude: string[];
  posted_within_days: (typeof POSTED_WITHIN_DAYS)[number] | null;
};

export type ApplicationEventRow = {
  id: string;
  application_id: string;
  user_id: string;
  status: ApplicationStatusRow;
  changed_at: string;
};

/** Ways the Tracker and Jobs can be sorted: by score either way, newest posting, or most recently added. */
export const JOB_SORTS = ["desc", "asc", "posted", "added"] as const;

export type JobSort = (typeof JOB_SORTS)[number];

export type HiddenCompanyRow = {
  user_id: string;
  company_id: string;
  hidden: boolean;
  created_at: string;
};

export type AgentRunRow = {
  id: string;
  user_id: string;
  kind: string;
  input: Record<string, unknown>;
  status: RunStatusRow;
  error: string | null;
  error_code: string | null;
  progress: string | null;
  usage: RunUsage | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export type Database = {
  // supabase-js reads this to pick its PostgREST behavior.
  __InternalSupabase: { PostgrestVersion: "12" };
  public: {
    Tables: {
      profiles: {
        Row: ProfileRow;
        Insert: Partial<ProfileRow> & Pick<ProfileRow, "user_id">;
        Update: Partial<ProfileRow>;
        Relationships: [];
      };
      resumes: {
        Row: ResumeRow;
        Insert: Partial<ResumeRow> & Pick<ResumeRow, "user_id" | "storage_path" | "file_name">;
        Update: Partial<ResumeRow>;
        Relationships: [];
      };
      postings: {
        Row: PostingRow;
        Insert: never;
        Update: never;
        Relationships: [];
      };
      applications: {
        Row: ApplicationRow;
        Insert: Partial<ApplicationRow> & Pick<ApplicationRow, "user_id" | "posting_id">;
        Update: Partial<ApplicationRow>;
        Relationships: [
          {
            foreignKeyName: "applications_posting_id_fkey";
            columns: ["posting_id"];
            isOneToOne: false;
            referencedRelation: "postings";
            referencedColumns: ["id"];
          },
        ];
      };
      application_events: {
        Row: ApplicationEventRow;
        Insert: never;
        Update: never;
        Relationships: [
          {
            foreignKeyName: "application_events_application_id_fkey";
            columns: ["application_id"];
            isOneToOne: false;
            referencedRelation: "applications";
            referencedColumns: ["id"];
          },
        ];
      };
      agent_runs: {
        Row: AgentRunRow;
        Insert: never;
        Update: never;
        Relationships: [];
      };
      companies: {
        Row: CompanyRow;
        Insert: never;
        Update: never;
        Relationships: [];
      };
      hidden_companies: {
        Row: HiddenCompanyRow;
        Insert: Partial<HiddenCompanyRow> & Pick<HiddenCompanyRow, "user_id" | "company_id">;
        Update: never;
        Relationships: [];
      };
    };
    Views: { [_ in never]: never };
    Functions: { [_ in never]: never };
    Enums: {
      job_source: JobSourceRow;
      application_status: ApplicationStatusRow;
      run_status: RunStatusRow;
      workplace_type: WorkplaceTypeRow;
      company_origin: CompanyOriginRow;
    };
    CompositeTypes: { [_ in never]: never };
  };
};
