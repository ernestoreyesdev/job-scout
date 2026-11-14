"use client";

import { LogOut, Moon, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { saveTheme } from "@/app/actions";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ThemeRow } from "@/lib/db";
import { createClient } from "@/lib/supabase/client";
import { applyTheme } from "@/lib/theme";

/**
 * The account menu behind a round button with the email's first letter: the email, a light or dark theme saved to
 * the account, and signing out, which sends the browser to the sign-in page.
 */
export function SignOut({ email, theme }: { email: string; theme: ThemeRow }) {
  const router = useRouter();
  const [selected, setSelected] = useState(theme);
  const [, startSaving] = useTransition();
  const [pending, startTransition] = useTransition();

  function chooseTheme(value: string) {
    const next: ThemeRow = value === "dark" ? "dark" : "light";
    setSelected(next);
    applyTheme(next);
    startSaving(async () => {
      await saveTheme(next);
    });
  }

  function signOut() {
    startTransition(async () => {
      await createClient()?.auth.signOut();
      router.push("/login");
      router.refresh();
    });
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Account"
        title={email}
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium uppercase outline-none hover:bg-muted/70 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {email[0]}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate text-sm font-normal text-foreground">{email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={selected} onValueChange={chooseTheme}>
          <DropdownMenuRadioItem value="light" onSelect={(event) => event.preventDefault()}>
            <Sun />
            Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark" onSelect={(event) => event.preventDefault()}>
            <Moon />
            Dark
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut} disabled={pending}>
          <LogOut />
          {pending ? "Signing out…" : "Sign out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
