"use client";

import { Moon, Sun } from "lucide-react";
import { useTransition } from "react";

import { saveTheme } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { applyTheme } from "@/lib/theme";

/** Flips between light and dark and saves the choice to the account; the icon shows the theme it switches to. */
export function ThemeToggle() {
  const [, startTransition] = useTransition();

  function toggle() {
    const next = document.documentElement.classList.contains("dark") ? "light" : "dark";
    applyTheme(next);
    startTransition(async () => {
      await saveTheme(next);
    });
  }

  return (
    <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Switch between light and dark" title="Switch theme">
      <Moon className="dark:hidden" />
      <Sun className="hidden dark:block" />
    </Button>
  );
}
