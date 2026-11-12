# job-finder

Finds jobs that match a user's resume, scores the fit, and tracks applications. The user always submits applications themselves.

## Structure

- `apps/web`: Next.js 16 (App Router, Tailwind v4, shadcn), to be deployed on Vercel
- `services/agent`: Python 3.12 FastAPI service that runs job searches, scoring and the other Claude calls (uv)
- `infra/supabase`: Postgres schema, row-level security and storage policies (`migrations/`), plus local stack config

The browser only talks to Next.js. Server actions call the agent with the user's Supabase access token; the agent verifies it with Supabase Auth and queries as that user, so row-level security applies.

## Security

- **Users' Anthropic keys** are encrypted by the agent with Fernet (`AGENT_ENCRYPTION_KEY`, from `services/agent/.env`) and stored in `api_credentials`. That table has row-level security on and no policies, so only the agent's service role can read it. The browser gets back the last four characters as a hint, never the key.
- **Row-level security** is on for every table. Per-user tables (`profiles`, `resumes`, `applications`, `application_events`, `agent_runs`, `hidden_companies`) only allow the signed-in user's own rows, and the agent reads and writes them with the user's token. Resume files live in a private `resumes` bucket under `{user_id}/`, with the same rule.
- **Shared data** (`postings`, `companies`) is readable by any signed-in user and written only by the agent's service role. `directory_discoveries` is service-role only. The service role is also used for `api_credentials`, and for nothing else.
- **Agent requests** need a Supabase access token, checked with Supabase Auth on every call. A user can have one run at a time (enforced by a unique index); a run still unfinished after 10 minutes is marked failed.
- **Job sources** are public job board pages and APIs that need no credentials. Text from postings and Hacker News posts is treated as data in every prompt, never as instructions.
- **Secrets** stay in `.env` files, which git ignores; only `.env.example` files are committed. Resume `.docx` files are ignored too.

## Getting started

Requirements: Node 24, Docker Desktop running, uv (`brew install uv`).

```bash
npm install
npx supabase start --workdir infra   # local Postgres, Auth, Storage; applies infra/supabase/migrations
cd services/agent && uv sync && cd ../..
```

Copy `apps/web/.env.example` to `apps/web/.env.local` and `services/agent/.env.example` to `services/agent/.env`, filling the keys from `npx supabase status --workdir infra`.

```bash
npm run dev:agent   # http://127.0.0.1:8001
npm run dev:web     # http://localhost:3000
```

Magic-link emails land in the local inbox at http://127.0.0.1:54324. Supabase Studio is at http://127.0.0.1:54323.

Other tasks: `npm run build`, `npm run lint`, `npm run typecheck` (through Turborepo) and `npm run test:agent` (pytest).

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push to `main` and every pull request: the agent's pytest suite with uv, and the web app's lint and typecheck. Neither job needs secrets; the tests mock every external API.
