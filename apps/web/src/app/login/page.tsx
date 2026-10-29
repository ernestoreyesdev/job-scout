import { Suspense } from "react";

import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        We&apos;ll email you a sign-in link, so there&apos;s no password to remember.
      </p>
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
