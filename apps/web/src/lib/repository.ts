import { redirect } from "next/navigation";

import { JobFinderRepository } from "@/lib/db";

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
export async function getSignedInSource(): Promise<SignedInSource> {
  const supabase = await createClient();
  if (!supabase) redirect("/login?error=config");

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return { repository: new JobFinderRepository(supabase), email: user.email, admin: user.app_metadata?.role === "admin" };
}

/** The signed-in admin's source; anyone else is sent to the Tracker. */
export async function getAdminSource(): Promise<SignedInSource> {
  const source = await getSignedInSource();
  if (!source.admin) redirect("/tracker");
  return source;
}
