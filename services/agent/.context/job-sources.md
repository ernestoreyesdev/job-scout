# Job Sources

The agent reads open jobs from the public job board APIs of applicant tracking systems (ATS). None of them need credentials. This document covers how the source layer is built and what each API looks like, as verified against the live APIs on 2026-10-29.

## Architecture

### File Locations

| File | Purpose |
|------|---------|
| `app/sources/base.py` | `Posting` (the normalized job), `BoardNotFound`, `CompanyNotFound`, and the abstract `JobSource` class |
| `app/sources/__init__.py` | Registry (`SOURCES`) and the functions the rest of the app calls: `find_company`, `fetch_board`, `describe`, `board_from_url`, `board_hosts`, `source_named` |
| `app/sources/<system>.py` | One `JobSource` subclass per system: its endpoints and how its JSON maps to `Posting`, nothing else |
| `app/sources/text.py` | Helpers adapters share: `html_to_text`, `join_locations`, `workplace_from_location` |
| `app/sources/filters.py` | Search filters applied after fetching: `matches_keywords`, `matches_workplace`, `matches_location`, `remote_in_us` |
| `supabase/migrations/*` | The `job_source` enum lists every system a posting or company row can come from |

### Layers

```
┌──────────────────────┐   ┌───────────────────────────┐   ┌──────────────────────┐
│ Orchestrator /        │──▶│ Registry (__init__.py)     │──▶│ JobSource subclass    │
│ discovery agent       │   │ find_company, fetch_board, │   │ fetch / describe      │
│                       │   │ describe, board_from_url   │   │ (per-system mapping)  │
└──────────────────────┘   └───────────────────────────┘   └──────────┬───────────┘
                                                                        │ inherits
                                                             ┌──────────▼───────────┐
                                                             │ JobSource (base.py)   │
                                                             │ HTTP client, 404 →    │
                                                             │ BoardNotFound, URL    │
                                                             │ parsing, name guesses │
                                                             └──────────────────────┘
```

Callers outside `app/sources/` only use the registry functions. They never import a specific system's module.

### What `JobSource` owns

| Member | Behavior | Override when |
|--------|----------|---------------|
| `fetch(board, company)` | Abstract. Returns every open posting on the board. Raises `BoardNotFound` when the board doesn't exist | Always implemented |
| `describe(posting)` | Returns `posting.description` | The system's job list omits descriptions (SmartRecruiters) |
| `board_candidates(company)` | Compact and hyphenated lowercase spellings: `Scale AI` → `scaleai`, `scale-ai` | The system names boards differently |
| `board_from_url(url)` | First path segment of a URL on one of `board_hosts`, lowercased, skipping `reserved_paths` | The board lives elsewhere in the URL (Recruitee subdomains, Workday) |
| `careers_url(board)` | The company's public job listing page: `https://{board_hosts[0]}/{board}`, saved on `companies.careers_url` whenever a company is checked | The page lives elsewhere (Greenhouse uses `job-boards.greenhouse.io`, Recruitee a subdomain, Workday `tenant.server/site`) |
| `default_name(board)` | Name shown for a newly discovered board until its jobs give one: `scale-ai` → `Scale Ai` | The board string isn't a name (Workday) |
| `_get_json(board, url, params)`, `_post_json(board, url, body)` | Request with the shared client; a status in `not_found_statuses` (404 by default) raises `BoardNotFound`; other errors raise | |

Class attributes each subclass sets: `name` (the enum value), `label` (for messages), `board_hosts` (public job page hosts, also used to limit discovery web searches; a parent domain such as `myworkdayjobs.com` also covers its subdomains in the search), and optionally `reserved_paths` (site pages that aren't boards) and `not_found_statuses`.

### Posting fields

| Field | Meaning |
|-------|---------|
| `source`, `board` | The system and the company's board name on it; together they identify a company in the `companies` table |
| `external_id` | The job's ID on that system; unique per `source` in the `postings` table |
| `title`, `company`, `url` | As shown to the user. `company` is the system's name for the company when it gives one, else the name the caller passed |
| `location` | All locations joined with `; ` |
| `description` | Plain text. May be empty when the job list omits it; `describe` fills it in before scoring |
| `posted_at` | Publication time, timezone aware |
| `workplace_type` | `onsite`, `hybrid`, `remote`, or null when the system doesn't say |

### Behavior shared across systems (outside `app/sources/`)

- **Lookup** (`find_company`): tries each system's name guesses; the board with the most postings wins, since companies that switch systems often leave a stale board behind. It returns a `CompanyBoard` (system, board, name, postings). A board with no postings still counts as found: some systems keep dormant accounts (Workable has empty `publix` and `cvshealth` accounts), and the search reports "Found Publix, but it has no open jobs listed." and records the company in the directory.
- **Web lookup** (`web_lookup` in the orchestrator): when no name guess matches, the run fails with `error_code = 'company_not_found'` and the Tracker offers "Search the web for {company}". That re-run sets `web_lookup` on the rule, which runs two web searches limited to `board_hosts()` and keeps only boards whose identifier or job company name contains the company's name (letters and digits, lowercase); the one with the most postings wins. It's the only way to reach Workday boards by company name. NVIDIA: 2 searches, about 2 cents.
- **Directory fetches** (`app/agents/orchestrator.py`): 8 boards at a time. A failure other than "not found" is retried once after 2 seconds, then reported as unreachable. Three "not found" answers in a row remove the company from the directory.
- **Board cache** (`cached_fetch` in the registry): each board's postings are kept in memory and reused for 6 hours (`CACHE_SECONDS`); a restart of the agent clears it. Boards that don't exist aren't kept.
- **Closed postings** (`mark_closed` in the orchestrator): after a board is read, the user's tracked postings it no longer lists get `postings.closed_at`, and ones it lists again are reopened. A fetch that hit its system's limit (`max_jobs`, Workday's 2,000) is skipped, since missing jobs may still be open. With the cache, a closing can show up to 6 hours late.
- **Descriptions** (`with_descriptions` in the orchestrator): fetched only for the jobs about to be scored, then saved to `postings`. A job whose description can't be fetched is skipped, not scored blind.
- **Discovery** (`app/agents/discovery/agent.py`): web searches limited to `board_hosts()`; result URLs go through `board_from_url` to find new boards. It runs on a search across all companies while the directory has fewer than 25 companies, or when the last run in `directory_discoveries` is over 7 days old. Each run is logged there with its keywords and how many boards it found and added.
- **Naming and kind** (`name_companies`): newly discovered boards get their company's name and kind (`employer`, `staffing`, `aggregator`, saved on `companies.kind`) from one small Haiku call that reads the titles of the search results that pointed to each board (`cvshealth.wd1/cvs_health_careers` → `CVS Health`, employer). A company found by name or web lookup is labeled the first time it's found. Searches across all companies skip staffing and aggregator companies unless the user chose Show (a `hidden_companies` row with `hidden = false`).
- **Countries in locations**: Lever's `country` code and SmartRecruiters' country code are written out as names (`IN` → `India`, so they can't be read as US state codes), and Ashby's address country is appended when the location text lacks it. The search filters rely on this to keep jobs outside the US out of searches with no location. Boards already in the directory keep their names. Systems whose jobs carry a company name (Greenhouse, SmartRecruiters, Workable, Recruitee) overwrite it with theirs on the next check.

## Adding a system

1. Verify the public endpoint by hand: a known company, an unknown one (does it 404?), pagination, and whether descriptions, locations, workplace type and dates are included.
2. Add `app/sources/<system>.py` with a `JobSource` subclass. Override only what differs from the defaults above.
3. Register the class in `SOURCES` in `app/sources/__init__.py` and add its name to `SourceName` in `base.py`.
4. Add a migration: `alter type public.job_source add value '<system>';`, and the same value to `JobSourceRow` in `apps/web/src/lib/db/schema.ts`.
5. Add `tests/test_<system>.py` (mocked with `respx`) and a URL case to `test_board_from_url_covers_every_system`.
6. Document the API below.

## Systems in use

### Greenhouse

| | |
|---|---|
| Endpoint | `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` |
| Unknown board | 404 |
| Pagination | None; one response holds every job |
| Description | `content`: entity-escaped HTML (unescaped, then converted to text) |
| Company name | `company_name` |
| Location | `location.name` |
| Workplace type | Not provided. Inferred from the location text: "remote" or "hybrid" in it, else null |
| Posted | `first_published`, falling back to `updated_at` |
| Job URL | `absolute_url` |
| Job page hosts | `boards.greenhouse.io`, `job-boards.greenhouse.io` (board is the first path segment; `embed`, `job-openings`, `jobs` are site pages) |

### Lever

| | |
|---|---|
| Endpoint | `GET https://api.lever.co/v0/postings/{board}?mode=json` |
| Unknown board | 404 |
| Pagination | None |
| Description | `descriptionPlain`, then each entry of `lists` (title plus HTML items), then `additionalPlain` |
| Company name | Not provided |
| Location | `categories.location` plus `categories.allLocations` |
| Workplace type | `workplaceType`: `onsite`, `hybrid`, `remote`; `unspecified` maps to null |
| Posted | `createdAt` (milliseconds since epoch) |
| Job URL | `hostedUrl` |
| Job page host | `jobs.lever.co` |
| Note | Large boards are large responses: Jobgether's was 52 MB with 4,291 jobs |

### Ashby

| | |
|---|---|
| Endpoint | `GET https://api.ashbyhq.com/posting-api/job-board/{board}` |
| Unknown board | 404 |
| Pagination | None |
| Description | `descriptionPlain` |
| Company name | Not provided |
| Location | `location` plus each `secondaryLocations[].location` |
| Workplace type | `workplaceType`: `OnSite`, `Hybrid`, `Remote`, or null. `isRemote` is unreliable (true for hybrid jobs) and is not used |
| Posted | `publishedAt` |
| Job URL | `jobUrl` |
| Listed | Jobs with `isListed: false` are skipped |
| Job page host | `jobs.ashbyhq.com` |

### SmartRecruiters

| | |
|---|---|
| List endpoint | `GET https://api.smartrecruiters.com/v1/companies/{board}/postings?limit=100&offset={n}` |
| Detail endpoint | `GET https://api.smartrecruiters.com/v1/companies/{board}/postings/{id}` |
| Unknown board | **200 with an empty list**, not 404. An empty board is treated as not found |
| Pagination | `limit` up to 100 with `offset`; `totalFound` gives the total. Bosch (5,038 jobs) takes 51 requests, about 30 seconds |
| Description | **Not in the list.** `describe` reads the detail endpoint's `jobAd.sections` (company description, job description, qualifications, additional information), each HTML |
| Company name | `company.name` |
| Location | `location.city`, `location.region`, `location.country` (a two-letter code) |
| Workplace type | `location.remote` → remote, `location.hybrid` → hybrid, else onsite |
| Posted | `releasedDate` |
| Job URL | Built as `https://jobs.smartrecruiters.com/{board}/{id}` (the detail endpoint's `postingUrl` adds a title slug; both open the job) |
| Board names | Case-insensitive (`BoschGroup` and `boschgroup` both work). Real IDs are often not the plain company name, so lookup rarely finds them; discovery is the main way in |
| Job page host | `jobs.smartrecruiters.com` |

### Workable

| | |
|---|---|
| Endpoint | `GET https://apply.workable.com/api/v1/widget/accounts/{board}?details=true` |
| Unknown board | 404. Board names are lowercase (`HuggingFace` 404s, `huggingface` works) |
| Pagination | None |
| Description | `description` (HTML), included because of `details=true` |
| Company name | Top-level `name` |
| Location | Each `locations[]` entry as city, region, country |
| Workplace type | Only `telecommuting` (true → remote); everything else is null |
| Posted | `published_on`, a date without time (stored as midnight UTC) |
| Job URL | `url` (`https://apply.workable.com/j/{shortcode}`, which has no board in it) |
| Job page host | `apply.workable.com` (board is the first path segment; `j` and `api` are site paths) |
| Not used | `POST /api/v3/accounts/{board}/jobs` also works and has a `workplace` field, but no descriptions |

### Recruitee

| | |
|---|---|
| Endpoint | `GET https://{board}.recruitee.com/api/offers/` |
| Unknown board | 404 |
| Pagination | None |
| Description | `description` then `requirements`, both HTML |
| Company name | `company_name` |
| Location | `location` |
| Workplace type | `remote`, `hybrid`, `on_site` booleans, checked in that order; all false → null |
| Posted | `published_at`, formatted `2026-10-28 13:21:58 UTC` |
| Job URL | `careers_url` (often the company's own careers domain) |
| Status | Only `status: published` offers are kept |
| Job page host | `{board}.recruitee.com`: the board is the **subdomain**, so `board_from_url` is overridden. Companies on a custom careers domain can't be found through discovery |

### Workday

**Not a published API.** These are the JSON endpoints Workday's own career pages call. They need no credentials, but Workday could change or block them without notice.

| | |
|---|---|
| List endpoint | `POST https://{tenant}.{server}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` with `{"limit": 20, "offset": n, "appliedFacets": {}, "searchText": ""}` |
| Detail endpoint | `GET https://{tenant}.{server}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}` |
| Board | Three values identify a company: tenant, server (`wd1`, `wd5`, `wd503`...) and site. Stored as `tenant.server/site`, lowercase, e.g. `nvidia.wd5/nvidiaexternalcareersite`. Site names are case-insensitive |
| Unknown board | 404 for an unknown site, **422** for an unknown tenant; both count as not found. A wrong server number also returns 422 |
| Pagination | **At most 20 per request** (50 or 100 return 400). **At most 2,000 jobs per query**: offsets past 2,000 return the first page again, so a bigger board is cut at 2,000. Only the first page's `total` is reliable (later pages can report 0). Pages after the first are read 8 at a time: NVIDIA's 2,000 jobs take about 15 seconds; one at a time took about 1.5 seconds per request |
| Search | `searchText` matches broadly ("software engineer", quoted or not, matched 1,779 of NVIDIA's 2,000), so it isn't used |
| Description | **Not in the list.** `describe` reads `jobPostingInfo.jobDescription` (HTML) from the detail endpoint |
| Company name | Not in the list. `default_name` uses the tenant (`cvshealth` → `Cvshealth`) |
| Location | `locationsText`, except that jobs in several places say only "6 Locations". For those, the main location comes from the path (`/job/US-CA-Santa-Clara/...` → `US CA Santa Clara and 5 more`). On NVIDIA this applied to about 37% of jobs |
| Workplace type | Not provided. Inferred from the location text ("Remote" in it); nothing marks on-site or hybrid |
| Posted | **Relative text only**: `Posted Today`, `Posted Yesterday`, `Posted 3 Days Ago`, `Posted 30+ Days Ago` (counted as 30 days). The detail endpoint's `startDate` is exact but isn't fetched for every job |
| Job ID | `externalPath` (e.g. `/job/US-CA-Remote/Senior-Engineer_JR2025019`); a few entries have no path and are skipped |
| Job URL | `https://{tenant}.{server}.myworkdayjobs.com/{site}{externalPath}` |
| Lookup | Boards can't be guessed from a company name (`board_candidates` returns nothing); they come from discovery |
| Job page host | `{tenant}.{server}.myworkdayjobs.com/{locale?}/{site}/...`, where the optional locale looks like `en-US` and `wday` paths are the API, not boards |
| Verified | NVIDIA (2,000 jobs), Workday (400), CVS Health (2,000, capped), Surescripts (23). One discovery call found 4 Workday boards among 25 |

## Systems checked but not in use

| System | Status |
|--------|--------|
| Personio, BambooHR | Test requests failed; endpoints not confirmed |
| IBM Kenexa BrassRing | Used by Publix. No public listing endpoint found; only reachable through an aggregator |
