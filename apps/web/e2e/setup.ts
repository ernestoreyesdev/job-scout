import { expect, test as setup } from "@playwright/test";
import { createClient } from "@supabase/supabase-js";

import { EMAIL, JOB_TITLE, RATED_TITLE, SEARCH_KEYWORDS } from "./test-user";

/** Local Supabase admin client; the service key comes from `supabase status`. */
function admin() {
  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!, {
    auth: { persistSession: false },
  });
}

setup("seed a user with two new jobs and a past search, and sign in by email link", async ({ page }) => {
  const db = admin();
  const { data: users, error: listError } = await db.auth.admin.listUsers();
  if (listError) throw listError;
  let user = users.users.find((candidate) => candidate.email === EMAIL);
  if (!user) {
    const { data, error } = await db.auth.admin.createUser({ email: EMAIL, email_confirm: true });
    if (error) throw error;
    user = data.user;
  }
  await db.from("applications").delete().eq("user_id", user.id);
  for (const [externalId, title] of [
    ["e2e-job", JOB_TITLE],
    ["e2e-rated-job", RATED_TITLE],
  ]) {
    const { data: posting, error: postingError } = await db
      .from("postings")
      .upsert(
        {
          source: "manual",
          board: "manual",
          external_id: externalId,
          title,
          company: "Playwright Labs",
          location: "Remote",
          url: `https://example.com/${externalId}`,
          description: "A job the browser tests track.",
        },
        { onConflict: "source,external_id" },
      )
      .select("id")
      .single();
    if (postingError) throw postingError;
    const { error: applicationError } = await db
      .from("applications")
      .insert({ user_id: user.id, posting_id: posting.id, status: "new", in_tracker: true });
    if (applicationError) throw applicationError;
  }
  await db.from("search_alerts").delete().eq("user_id", user.id);
  await db.from("agent_runs").delete().eq("user_id", user.id);
  const { error: profileError } = await db.from("profiles").upsert({ user_id: user.id, daily_emails: false });
  if (profileError) throw profileError;
  const { error: runError } = await db
    .from("agent_runs")
    .insert({ user_id: user.id, kind: "search", input: { keywords: [SEARCH_KEYWORDS] }, status: "done", progress: "Added 1 job." });
  if (runError) throw runError;

  const sent = Date.now();
  await page.goto("/login");
  await page.getByPlaceholder("you@example.com").fill(EMAIL);
  await page.getByRole("button", { name: "Email me a link" }).click();
  await page.goto(await signInLink(sent));
  await expect(page).toHaveURL(/\/tracker/);
  await page.context().storageState({ path: "e2e/.auth/user.json" });
});

/** The sign-in link from the newest email to EMAIL sent after `since`, read from the local Mailpit inbox. */
async function signInLink(since: number): Promise<string> {
  const inbox = process.env.MAILPIT_URL ?? "http://127.0.0.1:54324";
  for (let attempt = 0; attempt < 30; attempt++) {
    const search = await fetch(`${inbox}/api/v1/search?query=${encodeURIComponent(`to:${EMAIL}`)}`).then((res) => res.json());
    const message = search.messages?.find((candidate: { Created: string }) => new Date(candidate.Created).getTime() >= since - 1000);
    if (message) {
      const body = await fetch(`${inbox}/api/v1/message/${message.ID}`).then((res) => res.json());
      const link = (body.Text as string).match(/https?:\/\/\S+\/auth\/v1\/verify\S+/)?.[0];
      if (link) {
        // The link's path on the API these tests use, whatever host the local stack writes into emails.
        const emailed = new URL(link.replace(/[)\]>]+$/, ""));
        return new URL(emailed.pathname + emailed.search, process.env.NEXT_PUBLIC_SUPABASE_URL).href;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`No sign-in email reached ${EMAIL}.`);
}
