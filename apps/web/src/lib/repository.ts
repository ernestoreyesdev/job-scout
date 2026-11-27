import { redirect } from "next/navigation";
import { cache } from "react";

import { JobFinderRepository, type ProfileRow, type ResumeRow, type ThemeRow } from "@/lib/db";

import { createClient } from "./supabase/server";

export interface SignedInSource {
  repository: JobFinderRepository;
  email?: string;
  admin: boolean;
}

/**
 * The signed-in user's repository. Sends the browser to /login when nobody is
 * signed in, and to /login?error=config when Supabase isn't configured.
 */
export const getSignedInSource = cache(async (): Promise<SignedInSource> => {
  const signedIn = await currentUser();
  if (signedIn === undefined) redirect("/login?error=config");
  if (!signedIn) redirect("/login");

  const { supabase, user } = signedIn;
  return {
    repository: new JobFinderRepository(supabase, user.id),
    email: user.email,
    admin: user.app_metadata?.role === "admin",
  };
});

/** The signed-in admin's source; anyone else is sent to the Tracker. */
export async function getAdminSource(): Promise<SignedInSource> {
  const source = await getSignedInSource();
  if (!source.admin) redirect("/tracker");
  return source;
}

/** The Supabase client and signed-in user for this request: undefined without Supabase, null when signed out. */
export const currentUser = cache(async () => {
  const supabase = await createClient();
  if (!supabase) return undefined;
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user ? { supabase, user } : null;
});

/** The signed-in user's saved theme for this request, or null when signed out or not saved. */
export const currentTheme = cache(async (): Promise<ThemeRow | null> => (await currentProfile())?.theme ?? null);

/** The signed-in user's primary resume, read once per request. */
export const getPrimaryResume = cache(async (): Promise<ResumeRow | null> => {
  const { repository } = await getSignedInSource();
  return repository.getPrimaryResume();
});

/** The signed-in user's theme and daily email switch, read once per request; null when signed out or not saved. */
export const currentProfile = cache(async (): Promise<Pick<ProfileRow, "theme" | "daily_emails"> | null> => {
  const signedIn = await currentUser();
  if (!signedIn) return null;
  const { data } = await signedIn.supabase.from("profiles").select("theme, daily_emails").maybeSingle();
  return data;
});
