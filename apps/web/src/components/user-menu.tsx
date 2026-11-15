import { SignOut } from "@/components/sign-out";
import { currentTheme, currentUser } from "@/lib/repository";

/** The account menu for the signed-in user, with their saved theme; empty when nobody is signed in. */
export async function UserMenu() {
  const user = (await currentUser())?.user;
  if (!user?.email) return null;
  const theme = await currentTheme();

  return <SignOut email={user.email} theme={theme ?? "light"} admin={user.app_metadata?.role === "admin"} />;
}
