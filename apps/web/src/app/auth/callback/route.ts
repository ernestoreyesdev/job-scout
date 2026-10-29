import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

/** Turns the magic-link code into a session cookie, then lands on the tracker. */
export async function GET(request: NextRequest) {
  const { searchParams, protocol, host } = new URL(request.url);
  // request.url names the dev server's own host; the Host header is the address the browser used.
  const origin = `${protocol}//${request.headers.get("host") ?? host}`;
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/tracker";

  if (code) {
    const supabase = await createClient();
    const { error } = (await supabase?.auth.exchangeCodeForSession(code)) ?? {
      error: new Error("Supabase is not configured"),
    };
    if (!error) return NextResponse.redirect(`${origin}${next}`);
  }

  return NextResponse.redirect(`${origin}/login?error=link`);
}
