# job-finder

Finds jobs that match a user's resume, scores the fit, and tracks applications. The user always submits applications themselves.

## Structure

- `apps/web`: Next.js 16 (App Router, Tailwind v4, shadcn), to be deployed on Vercel
- `services/agent`: Python 3.12 FastAPI service that runs the Claude tool-use loop (uv)
- `supabase`: Postgres schema, row-level security and storage policies (`migrations/`), plus local stack config

The browser only talks to Next.js. Server actions call the agent with the user's Supabase access token; the agent verifies it with Supabase Auth and queries as that user, so row-level security applies. The service role is used only for `api_credentials` and `postings` writes. Each user's Anthropic key is encrypted by the agent and never sent back to the browser.

## Getting started

Requirements: Node 24, Docker Desktop running, uv (`brew install uv`).

```bash
npm install
npx supabase start          # local Postgres, Auth, Storage; applies supabase/migrations
cd services/agent && uv sync && cd ../..
```

Copy `apps/web/.env.example` to `apps/web/.env.local` and `services/agent/.env.example` to `services/agent/.env`, filling the keys from `npx supabase status`.

```bash
npm run dev:agent   # http://127.0.0.1:8000
npm run dev:web     # http://localhost:3000
```

Magic-link emails land in the local inbox at http://127.0.0.1:54324. Supabase Studio is at http://127.0.0.1:54323.

Other tasks: `npm run build`, `npm run lint`, `npm run typecheck` (through Turborepo) and `npm run test:agent` (pytest).
