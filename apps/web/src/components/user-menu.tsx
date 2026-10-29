import { SignOut } from "@/components/sign-out";
import { createClient } from "@/lib/supabase/server";

/** Signed-in email and sign-out button; empty when nobody is signed in. */
export async function UserMenu() {
  const supabase = await createClient();
  const user = supabase ? (await supabase.auth.getUser()).data.user : null;
  if (!user?.email) return null;

  return <SignOut email={user.email} />;
}
