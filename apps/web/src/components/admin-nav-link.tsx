import { NavItem } from "@/components/nav-links";
import { currentUser, isAdmin } from "@/lib/repository";

/** The Admin nav link, shown only to users with the admin role. */
export async function AdminNavLink() {
  const user = (await currentUser())?.user;
  if (!user || !isAdmin(user)) return null;
  return <NavItem href="/admin" label="Admin" />;
}
