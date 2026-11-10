import { createClient } from "@/lib/supabase/server";
import { themeSyncScript } from "@/lib/theme";

/** Applies the signed-in user's saved theme, so a choice made on another device carries over; empty when signed out. */
export async function ThemeSync() {
  const supabase = await createClient();
  const user = supabase ? (await supabase.auth.getUser()).data.user : null;
  if (!supabase || !user) return null;
  const { data } = await supabase.from("profiles").select("theme").maybeSingle();
  if (!data) return null;

  return <script dangerouslySetInnerHTML={{ __html: themeSyncScript(data.theme) }} />;
}
