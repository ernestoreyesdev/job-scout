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
  | "gem"
  | "rippling"
  | "pinpoint"
  | "teamtailor"
  | "polymer"
  | "oracle"
  | "hackernews"
  | "manual";

export const APPLICATION_STATUSES = ["new", "saved", "applied", "interviewing", "offer", "rejected"] as const;
export const STATUS_LABELS: Record<(typeof APPLICATION_STATUSES)[number], string> = {
  new: "New",
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
};

/** Statuses a job applied to outside the app can be added with. */
export const OUTSIDE_STATUSES = ["applied", "interviewing", "offer", "rejected"] as const;

/** Funnel stages after applying, in order; reaching one counts every stage before it too. */
export const FUNNEL_STAGES = ["applied", "interviewing", "offer"] as const;

/** A still-listed posting this many days old is flagged as a possible ghost job. */
export const GHOST_JOB_DAYS = 60;


/** A posting counts as reposted when the same title went up at the company at least this many days earlier. */
export const REPOST_DAYS = 15;

export type ApplicationStatusRow = (typeof APPLICATION_STATUSES)[number];

/** Which page's jobs a rescore scores. */
export type RescoreScope = "tracker" | "jobs";

export type RunStatusRow = "queued" | "running" | "done" | "failed" | "stopped";

export const WORKPLACE_TYPES = ["onsite", "hybrid", "remote"] as const;

export type WorkplaceTypeRow = (typeof WORKPLACE_TYPES)[number];

export const WORKPLACE_LABELS = { onsite: "On-site", hybrid: "Hybrid", remote: "Remote" } as const;

export type CompanyOriginRow = "lookup" | "discovery" | "import" | "link" | "hacker_news";

export type CompanyKindRow = "employer" | "staffing" | "aggregator";

/** Kinds never searched, whatever the user chose. */
export const SKIPPED_COMPANY_KINDS: readonly CompanyKindRow[] = ["staffing"];

export const POSTED_WITHIN_DAYS = [1, 3, 7, 14, 30] as const;

/** The lowest scores of the Strong fit and Possible fit labels. */
export const STRONG_FIT_SCORE = 70;
export const POSSIBLE_FIT_SCORE = 50;

/** Lowest fit score a scored search keeps, matching the Possible and Strong fit labels. */
export const MIN_SCORES = [POSSIBLE_FIT_SCORE, STRONG_FIT_SCORE] as const;

/** Upper bound the agent accepts for jobs scored in one search, and the form's starting value. */
export const MAX_JOBS_PER_SEARCH = 25;
export const DEFAULT_JOBS_PER_SEARCH = 10;

/** Longest company name or location a search takes. */
export const MAX_FIELD_LENGTH = 100;

/** Upper bound the agent accepts for companies added in one import, and for one entry's length. */
export const MAX_COMPANY_IMPORT = 100;
export const MAX_IMPORT_ENTRY_LENGTH = 300;

/** Most jobs a daily match email lists, as the agent caps it. */
export const DAILY_EMAIL_MATCHES = 10;

/** The page signing in and the logo lead to. */
export const HOME_PATH = "/tracker";
/** The Tracker's view of jobs the user rated. */
export const RATED_PATH = "/tracker?view=rated";

export const BYTES_PER_MB = 1024 * 1024;
export const DAY_MS = 24 * 60 * 60 * 1000;

/** Largest resume upload, and the file types a resume can be with their media types. */
export const MAX_RESUME_MB = 1;
export const RESUME_TYPES = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
} as const;

/** How many of the user's latest different searches the daily email dialog offers. */
export const DAILY_SEARCH_CHOICES = 5;

/** Past search runs read to find the DAILY_SEARCH_CHOICES different searches. */
export const DAILY_SEARCH_SCAN = 50;

export type ProfileRow = {
  user_id: string;
  anthropic_key_hint: string | null;
  theme: ThemeRow;
  daily_emails: boolean;
  lessons_fingerprint: string | null;
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
  description_hash: string | null;
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
  edited_title: string | null;
  edited_company: string | null;
  edited_description: string | null;
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
  page: string;
  metric: (typeof WEB_VITALS)[number];
  value: number;
  rating: string | null;
  navigation_type: string | null;
  created_at: string;
};

/** A search the user marked to run each morning, emailing them its new strong matches; `rule` is the run's input. */
export type SearchAlertRow = {
  id: string;
  user_id: string;
  rule: Record<string, unknown>;
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
  user_id: string | null;
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

/** A run's kind, input, status and progress, as the pages show it. */
export type RunSummary = Omit<AgentRunRow, "usage" | "timings">;

/** A learned lesson no update has confirmed for this many days stops counting. */
export const LESSON_FADE_DAYS = 60;

export const MAX_LESSON_LENGTH = 200;

/** A preference the user wrote, or one learned from their ratings and statuses; a deleted one keeps its row. */
export type LessonRow = {
  id: string;
  user_id: string;
  text: string;
  source: "learned" | "user";
  evidence: number;
  confirmed_at: string;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
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
      search_alerts: {
        Row: SearchAlertRow;
        Insert: Pick<SearchAlertRow, "user_id" | "rule">;
        Update: never;
        Relationships: [];
      };
      lessons: {
        Row: LessonRow;
        Insert: Pick<LessonRow, "user_id" | "text" | "source">;
        Update: Pick<LessonRow, "deleted_at">;
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
      admin_storage: { Args: Record<string, never>; Returns: { bytes: number; unembedded: number } };
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

/** Whether a company's kind keeps it out of every search. */
export function isSkippedKind(kind: CompanyKindRow | null): boolean {
  return kind !== null && SKIPPED_COMPANY_KINDS.includes(kind);
}
