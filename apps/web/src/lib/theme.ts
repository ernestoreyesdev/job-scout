import type { ThemeRow } from "@/lib/db";

const STORAGE_KEY = "theme";

/** Runs before the first paint: applies the theme this browser last saw, so dark pages never flash white. */
export const THEME_BOOT_SCRIPT = `try{if(localStorage.getItem("${STORAGE_KEY}")==="dark")document.documentElement.classList.add("dark")}catch(e){}`;

/** Switches the page to `theme` now and remembers it in this browser. */
export function applyTheme(theme: ThemeRow): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {}
}

/** The same as applyTheme, as an inline script for a server-rendered page. */
export function themeSyncScript(theme: ThemeRow): string {
  return `try{document.documentElement.classList.toggle("dark",${JSON.stringify(theme)}==="dark");localStorage.setItem("${STORAGE_KEY}",${JSON.stringify(theme)})}catch(e){}`;
}
