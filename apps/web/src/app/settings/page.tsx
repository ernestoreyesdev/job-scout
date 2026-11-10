import { Suspense } from "react";

import { KeyForm } from "@/components/key-form";
import { ThemeForm } from "@/components/theme-form";
import { getSignedInSource } from "@/lib/repository";

export default function SettingsPage() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <section className="mt-8">
        <h2 className="font-medium">Anthropic API key (optional)</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Searches and fit scores run on the app&apos;s shared key unless you add your own. Your key is encrypted on the
          server and never shown again; only its last four characters are kept for display.
        </p>
        <Suspense fallback={<p className="mt-4 text-sm text-muted-foreground">Loading…</p>}>
          <KeySection />
        </Suspense>
      </section>
      <section className="mt-10">
        <h2 className="font-medium">Appearance</h2>
        <p className="mt-1 text-sm text-muted-foreground">Your choice is saved to your account and used on every device.</p>
        <Suspense fallback={<p className="mt-4 text-sm text-muted-foreground">Loading…</p>}>
          <ThemeSection />
        </Suspense>
      </section>
    </main>
  );
}

async function KeySection() {
  const { repository } = await getSignedInSource();
  const profile = await repository.getProfile();
  return <KeyForm hint={profile?.anthropic_key_hint ?? null} />;
}

async function ThemeSection() {
  const { repository } = await getSignedInSource();
  const profile = await repository.getProfile();
  const theme = profile?.theme ?? "light";
  return <ThemeForm key={theme} theme={theme} />;
}
