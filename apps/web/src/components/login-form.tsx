"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";

type Status = { kind: "idle" | "sending" | "sent" } | { kind: "error"; message: string };

const LINK_ERRORS: Record<string, string> = {
  link: "That sign-in link is invalid or expired. Request a new one.",
  config: "Supabase is not configured yet.",
};

export function LoginForm() {
  const linkError = LINK_ERRORS[useSearchParams().get("error") ?? ""];
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    const supabase = createClient();
    if (!supabase) {
      setStatus({ kind: "error", message: LINK_ERRORS.config });
      return;
    }

    setStatus({ kind: "sending" });
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });

    setStatus(error ? { kind: "error", message: error.message } : { kind: "sent" });
  }

  return (
    <>
      <form onSubmit={signIn} className="mt-6 space-y-3">
        <Input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
        />
        <Button type="submit" className="w-full" disabled={status.kind === "sending"}>
          {status.kind === "sending" ? "Sending…" : "Email me a link"}
        </Button>
      </form>

      {status.kind === "sent" && (
        <p className="mt-4 text-sm text-green-700 dark:text-green-400">Check {email} for the sign-in link.</p>
      )}
      {status.kind === "error" && <p className="mt-4 text-sm text-destructive">{status.message}</p>}
      {status.kind === "idle" && linkError && <p className="mt-4 text-sm text-destructive">{linkError}</p>}
    </>
  );
}
