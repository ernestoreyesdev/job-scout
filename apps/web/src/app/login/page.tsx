import type { Metadata } from "next";
import { Briefcase } from "lucide-react";
import { Suspense } from "react";

import { LoginForm } from "@/components/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm rounded-2xl border bg-card p-8 text-card-foreground shadow-sm">
        <div className="flex size-11 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Briefcase className="size-5" />
        </div>
        <h1 className="mt-5 text-2xl font-semibold tracking-tight">Sign in to Job Scout</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          We&apos;ll email you a sign-in link, so there&apos;s no password to remember.
        </p>
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
