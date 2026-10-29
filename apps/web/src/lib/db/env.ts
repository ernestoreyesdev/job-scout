/**
 * Supabase connection values. Both are public by design: the anon key only
 * works alongside row-level security.
 */
export interface SupabaseEnv {
  url: string;
  anonKey: string;
}

export function readSupabaseEnv(
  env: Record<string, string | undefined> = process.env,
): SupabaseEnv | null {
  const url = env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  return url && anonKey ? { url, anonKey } : null;
}

/** True once the project has been pointed at a Supabase instance. */
export function isSupabaseConfigured(
  env: Record<string, string | undefined> = process.env,
): boolean {
  return readSupabaseEnv(env) !== null;
}
