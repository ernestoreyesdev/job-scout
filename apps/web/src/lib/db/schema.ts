/**
 * Hand-written row shapes for the tables in `infra/supabase/migrations`, so the app builds without the Supabase CLI.
 * They must stay type aliases: supabase-js requires `Record<string, unknown>`, which an interface doesn't satisfy, and
 * every query result would silently become `never`.
 */
export type JobSourceRow =
  | "greenhouse"
  | "lever"
  | "ashby"
  | "smartrecruiters"
  | "workable"
  | "recruitee"
  | "workday"
  | "personio"
  | "bamboohr"
  | "icims"
  | "jobvite"
  | "hackernews"
  | "manual";

export const APPLICATION_STATUSES = ["new", "saved", "applied", "interviewing", "offer", "rejected"] as const;

/** Statuses a job applied to outside the app can be added with. */
export const OUTSIDE_STATUSES = ["applied", "interviewing", "offer", "rejected"] as const;

/** Funnel stages after applying, in order; reaching one counts every stage before it too. */
export const FUNNEL_STAGES = ["applied", "interviewing", "offer"] as const;

/** A still-listed posting this many days old is flagged as a possible ghost job. */
export const GHOST_JOB_DAYS = 60;

/** An application still "applied" this many days after it was marked so gets a follow-up reminder. */
export const FOLLOW_UP_DAYS = 7;

/** A posting counts as reposted when the same title went up at the company at least this many days earlier. */
export const REPOST_DAYS = 15;

export type ApplicationStatusRow = (typeof APPLICATION_STATUSES)[number];

/** Which page's jobs a rescore scores. */
export type RescoreScope = "tracker" | "jobs";

export type RunStatusRow = "queued" | "running" | "done" | "failed" | "stopped";

export const WORKPLACE_TYPES = ["onsite", "hybrid", "remote"] as const;

export type WorkplaceTypeRow = (typeof WORKPLACE_TYPES)[number];

export type CompanyOriginRow = "lookup" | "discovery" | "import";

export type CompanyKindRow = "employer" | "staffing" | "aggregator";

/** Kinds a search skips unless the user chose to show the company. */
export const SKIPPED_COMPANY_KINDS: readonly CompanyKindRow[] = ["staffing", "aggregator"];

export const POSTED_WITHIN_DAYS = [1, 3, 7, 14, 30] as const;

/** Lowest fit score a scored search keeps, matching the Possible and Strong fit labels. */
export const MIN_SCORES = [50, 70] as const;

/** Upper bound the agent accepts for jobs scored in one search. */
export const MAX_JOBS_PER_SEARCH = 25;

/** Upper bound the agent accepts for companies added in one import. */
export const MAX_COMPANY_IMPORT = 100;

export type ProfileRow = {
  user_id: string;
  anthropic_key_hint: string | null;
  theme: ThemeRow;
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
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: SalaryPeriodRow | null;
  clearance: string | null;
  visa_sponsorship: "yes" | "no" | null;
  years_experience: number | null;
  tech_stack: string[];
  details_extracted_at: string | null;
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
  added_by: "search" | "user";
  fit_label: FitLabelRow | null;
  gap_analysis: GapAnalysis | null;
  gap_analyzed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type GapItem = { requirement: string; evidence: string; suggestion: string };

/** A job's requirements sorted against the resume, with how to talk about each. */
export type GapAnalysis = { covered: GapItem[]; weak: GapItem[]; missing: GapItem[] };

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
  score: boolean;
  min_score: (typeof MIN_SCORES)[number] | null;
};

export type ApplicationEventRow = {
  id: string;
  application_id: string;
  user_id: string;
  status: ApplicationStatusRow;
  changed_at: string;
};

/** Ways the Tracker and Jobs can be sorted: by score either way, newest posting, or most recently added. */
export const JOB_SORTS = ["desc", "asc", "posted", "added", "status"] as const;

/** Companies page columns that sort, each with the direction it starts in. */
export const COMPANY_SORTS = { name: "asc", jobs: "desc", checked: "desc" } as const;

export type CompanySort = keyof typeof COMPANY_SORTS;

export const FIT_LABELS = ["good", "bad"] as const;

export type FitLabelRow = (typeof FIT_LABELS)[number];

export const THEMES = ["light", "dark"] as const;

export type ThemeRow = (typeof THEMES)[number];

export type SalaryPeriodRow = "year" | "month" | "week" | "day" | "hour";

export type JobSort = (typeof JOB_SORTS)[number];

/** Core Web Vitals plus READY, the time until a page's data is on screen. */
export const WEB_VITALS = ["TTFB", "FCP", "LCP", "CLS", "INP", "READY"] as const;

/** One page load measurement a browser reported. */
export type WebVitalRow = {
  id: string;
  user_id: string;
  page: string;
  metric: (typeof WEB_VITALS)[number];
  value: number;
  rating: string | null;
  navigation_type: string | null;
  created_at: string;
};

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
  timings: Record<string, number> | null;
  jobs_added: number | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

/** The database shape supabase-js types queries with; `__InternalSupabase` sets its PostgREST behavior. */
export type Database = {
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
          {
            foreignKeyName: "applications_resume_id_fkey";
            columns: ["resume_id"];
            isOneToOne: false;
            referencedRelation: "resumes";
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
      web_vitals: {
        Row: WebVitalRow;
        Insert: Pick<WebVitalRow, "page" | "metric" | "value" | "rating" | "navigation_type">;
        Update: never;
        Relationships: [];
      };
    };
    Views: { [_ in never]: never };
    Functions: {
      reposted_postings: { Args: { job_ids: string[]; days: number }; Returns: { id: string }[] };
      admin_stats: { Args: Record<string, never>; Returns: Record<string, unknown> };
    };
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
