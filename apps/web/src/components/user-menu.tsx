import { SignOut } from "@/components/sign-out";
import { createClient } from "@/lib/supabase/server";

/** The account menu for the signed-in user, with their saved theme; empty when nobody is signed in. */
export async function UserMenu() {
  const supabase = await createClient();
  const user = supabase ? (await supabase.auth.getUser()).data.user : null;
  if (!supabase || !user?.email) return null;
  const { data } = await supabase.from("profiles").select("theme").maybeSingle();

  return <SignOut email={user.email} theme={data?.theme ?? "light"} admin={user.app_metadata?.role === "admin"} />;
}
