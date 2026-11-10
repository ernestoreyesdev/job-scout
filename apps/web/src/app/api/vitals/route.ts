import type { NextRequest } from "next/server";

import { WEB_VITALS, type WebVitalRow } from "@/lib/db";
import { createClient } from "@/lib/supabase/server";

const MAX_PAGE_LENGTH = 200;

/** Saves one web vitals measurement for the signed-in user; malformed ones get a 400, and signed-out ones are dropped by RLS. */
export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => null)) as Partial<Record<string, unknown>> | null;
  const metric = body?.metric;
  const value = body?.value;
  const page = typeof body?.page === "string" ? body.page.slice(0, MAX_PAGE_LENGTH) : "";
  if (!WEB_VITALS.includes(metric as WebVitalRow["metric"]) || typeof value !== "number" || !Number.isFinite(value) || !page.startsWith("/")) {
    return new Response(null, { status: 400 });
  }

  const supabase = await createClient();
  await supabase?.from("web_vitals").insert({
    page,
    metric: metric as WebVitalRow["metric"],
    value,
    rating: typeof body?.rating === "string" ? body.rating : null,
    navigation_type: typeof body?.navigationType === "string" ? body.navigationType : null,
  });
  return new Response(null, { status: 204 });
}
