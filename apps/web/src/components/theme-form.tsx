"use client";

import { Moon, Sun } from "lucide-react";
import { useState, useTransition } from "react";

import { saveTheme } from "@/app/actions";
import type { ThemeRow } from "@/lib/db";
import { applyTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { theme: "light", label: "Light", Icon: Sun },
  { theme: "dark", label: "Dark", Icon: Moon },
] as const;

/** Light or dark: switches the page at once and saves the choice to the account. */
export function ThemeForm({ theme }: { theme: ThemeRow }) {
  const [selected, setSelected] = useState(theme);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  function choose(next: ThemeRow) {
    setSelected(next);
    applyTheme(next);
    startTransition(async () => {
      const result = await saveTheme(next);
      setError(result.ok ? null : (result.error ?? "Could not save the theme."));
    });
  }

  return (
    <div className="mt-4">
      <div role="radiogroup" aria-label="Theme" className="grid max-w-sm grid-cols-2 gap-3">
        {OPTIONS.map(({ theme: option, label, Icon }) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={selected === option}
            onClick={() => choose(option)}
            className={cn(
              "flex items-center gap-2 rounded-xl border bg-card px-4 py-3 text-sm shadow-xs transition-colors hover:border-foreground/30",
              selected === option && "border-primary ring-2 ring-primary/20",
            )}
          >
            <Icon className="size-4" />
            {label}
          </button>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </div>
  );
}
