import { timingSafeEqual } from "node:crypto";

import type { NextRequest } from "next/server";

import { startBoardRefresh } from "@/lib/agent";

/** Vercel Cron's daily call: checks the cron secret and starts the agent's board refresh. */
export async function GET(request: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret) return new Response("CRON_SECRET is not configured.", { status: 503 });

  const authorization = request.headers.get("authorization") ?? "";
  const expected = Buffer.from(`Bearer ${secret}`);
  const given = Buffer.from(authorization);
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) {
    return new Response("Not allowed.", { status: 401 });
  }

  return new Response(null, { status: await startBoardRefresh(authorization) });
}
