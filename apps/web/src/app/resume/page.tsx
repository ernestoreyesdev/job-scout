import { FileText } from "lucide-react";
import { Suspense } from "react";

import { ResumeUpload } from "@/components/resume-upload";
import { SectionCard } from "@/components/section-card";
import { getSignedInSource } from "@/lib/repository";

export default function ResumePage() {
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Resume</h1>
      <p className="mt-1 text-sm text-muted-foreground">Fit scores use the text extracted from your latest upload.</p>
      <div className="mt-8 space-y-6">
        <SectionCard title="Upload a resume">
          <ResumeUpload />
        </SectionCard>
        <Suspense fallback={<div className="h-40 animate-pulse rounded-xl border bg-card" />}>
          <PrimaryResume />
        </Suspense>
      </div>
    </main>
  );
}

async function PrimaryResume() {
  const { repository } = await getSignedInSource();
  const resume = await repository.getPrimaryResume();
  if (!resume) return null;

  return (
    <SectionCard
      title="Current resume"
      description={
        <span className="inline-flex items-center gap-1.5">
          <FileText className="size-4" />
          {resume.file_name} · uploaded {resume.created_at.slice(0, 10)}
        </span>
      }
    >
      {resume.text ? (
        <pre className="max-h-[32rem] overflow-auto rounded-lg bg-muted/50 p-4 font-sans text-sm whitespace-pre-wrap">
          {resume.text}
        </pre>
      ) : (
        <p className="text-sm text-muted-foreground">Text hasn&apos;t been extracted yet.</p>
      )}
    </SectionCard>
  );
}
