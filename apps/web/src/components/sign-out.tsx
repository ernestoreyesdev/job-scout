"use client";

import { LogOut, Moon, Sun, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { deleteAccount, saveTheme } from "@/app/actions";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ThemeRow } from "@/lib/db";
import { createClient } from "@/lib/supabase/client";
import { applyTheme } from "@/lib/theme";

/**
 * The account menu behind a round button with the email's first letter: the email, a light or dark theme saved to
 * the account, signing out and, for anyone but an admin, deleting the account once the email is typed to confirm.
 * Signing out or deleting sends the browser to the sign-in page.
 */
export function SignOut({ email, theme, admin }: { email: string; theme: ThemeRow; admin: boolean }) {
  const router = useRouter();
  const [selected, setSelected] = useState(theme);
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [, startSaving] = useTransition();
  const [pending, startTransition] = useTransition();
  const [deleting, startDeleting] = useTransition();

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

  function openConfirm(open: boolean) {
    setConfirming(open);
    setTyped("");
    setError(null);
  }

  function remove() {
    startDeleting(async () => {
      const result = await deleteAccount();
      if (!result.ok) {
        setError(result.error ?? "Could not delete the account.");
        return;
      }
      await createClient()?.auth.signOut({ scope: "local" });
      router.push("/login");
      router.refresh();
    });
  }

  return (
    <>
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
          {!admin && (
            <DropdownMenuItem variant="destructive" onSelect={() => openConfirm(true)}>
              <Trash2 />
              Delete account
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <AlertDialog open={confirming} onOpenChange={(open) => !deleting && openConfirm(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete your account?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes your resume, your tracked jobs with their notes and statuses, and your sign-in. It can&apos;t be
              undone. The searches you ran and the scores your jobs got stay in the app&apos;s statistics, with nothing
              that links them to you.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="confirm-email">Type {email} to confirm</Label>
            <Input
              id="confirm-email"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <Button variant="destructive" onClick={remove} disabled={deleting || typed.trim().toLowerCase() !== email.toLowerCase()}>
              {deleting ? "Deleting…" : "Delete account"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
