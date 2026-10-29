"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

/** Ends the session and sends the browser to the sign-in page. */
export function SignOut({ email }: { email: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function signOut() {
    startTransition(async () => {
      await createClient()?.auth.signOut();
      router.push("/login");
      router.refresh();
    });
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-muted-foreground">{email}</span>
      <Button variant="outline" size="sm" onClick={signOut} disabled={pending}>
        {pending ? "Signing out…" : "Sign out"}
      </Button>
    </div>
  );
}
