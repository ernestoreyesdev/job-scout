import { NavItem } from "@/components/nav-links";
import { createClient } from "@/lib/supabase/server";

/** The Admin nav link, shown only to users with the admin role. */
export async function AdminNavLink() {
  const supabase = await createClient();
  const user = supabase ? (await supabase.auth.getUser()).data.user : null;
  if (user?.app_metadata?.role !== "admin") return null;
  return <NavItem href="/admin" label="Admin" />;
}
