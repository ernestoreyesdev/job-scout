import { readSupabaseEnv } from "@/lib/db";
import type { Database } from "@/lib/db";
import { createServerClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { connection } from "next/server";

/**
 * Supabase client for server components and route handlers, reading the
 * session from cookies. Null when the project has no Supabase credentials yet.
 */
export async function createClient(): Promise<SupabaseClient<Database> | null> {
  // Session checks read the clock, so every server client runs at request time.
  await connection();
  const env = readSupabaseEnv();
  if (!env) return null;

  const cookieStore = await cookies();

  return createServerClient<Database>(env.url, env.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Server components can't set cookies; middleware refreshes the
          // session instead, so this is safe to ignore.
        }
      },
    },
  });
}
