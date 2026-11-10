import { Suspense } from "react";

import { SectionCard } from "@/components/section-card";
import { ThemeForm } from "@/components/theme-form";
import { getSignedInSource } from "@/lib/repository";

export default function SettingsPage() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <div className="mt-8 space-y-6">
        <SectionCard title="Appearance" description="Your choice is saved to your account and used on every device.">
          <Suspense fallback={<div className="h-12 max-w-sm animate-pulse rounded-xl bg-muted" />}>
            <ThemeSection />
          </Suspense>
        </SectionCard>
      </div>
    </main>
  );
}

async function ThemeSection() {
  const { repository } = await getSignedInSource();
  const profile = await repository.getProfile();
  const theme = profile?.theme ?? "light";
  return <ThemeForm key={theme} theme={theme} />;
}
