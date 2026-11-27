import { SignOut } from "@/components/sign-out";
import { currentProfile, currentUser, isAdmin } from "@/lib/repository";

/** The account menu for the signed-in user, with their saved theme and daily email switch; empty when nobody is signed in. */
export async function UserMenu() {
  const user = (await currentUser())?.user;
  if (!user?.email) return null;
  const profile = await currentProfile();

  return (
    <SignOut
      email={user.email}
      theme={profile?.theme ?? "light"}
      dailyEmails={profile?.daily_emails ?? false}
      admin={isAdmin(user)}
    />
  );
}
