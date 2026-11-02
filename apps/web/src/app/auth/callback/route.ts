import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

/** Turns the magic-link code into a session cookie, then lands on the tracker. */
export async function GET(request: NextRequest) {
  const { searchParams, protocol, host } = new URL(request.url);
  // SITE_URL when deployed; locally the Host header is the address the browser used.
  const origin = process.env.SITE_URL?.replace(/\/+$/, "") || `${protocol}//${request.headers.get("host") ?? host}`;
  const code = searchParams.get("code");
  const requested = searchParams.get("next") ?? "";
  // Only a path on this site, so a sign-in link can't send the user to another one.
  const next = /^\/(?![\/\\])/.test(requested) ? requested : "/tracker";

  if (code) {
    const supabase = await createClient();
    const { error } = (await supabase?.auth.exchangeCodeForSession(code)) ?? {
      error: new Error("Supabase is not configured"),
    };
    if (!error) return NextResponse.redirect(`${origin}${next}`);
  }

  return NextResponse.redirect(`${origin}/login?error=link`);
}
