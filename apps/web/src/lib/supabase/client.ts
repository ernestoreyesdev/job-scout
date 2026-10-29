"use client";

import { readSupabaseEnv } from "@/lib/db";
import type { Database } from "@/lib/db";
import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Browser-side Supabase client. Reads the same public env vars as the server
 * client; returns null when the project isn't configured yet.
 */
export function createClient(): SupabaseClient<Database> | null {
  const env = readSupabaseEnv({
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  });
  if (!env) return null;

  return createBrowserClient<Database>(env.url, env.anonKey);
}
