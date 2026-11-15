import { currentTheme } from "@/lib/repository";
import { themeSyncScript } from "@/lib/theme";

/** Applies the signed-in user's saved theme, so a choice made on another device carries over; empty when signed out. */
export async function ThemeSync() {
  const theme = await currentTheme();
  if (!theme) return null;

  return <script dangerouslySetInnerHTML={{ __html: themeSyncScript(theme) }} />;
}
