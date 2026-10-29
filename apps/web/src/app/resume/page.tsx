import { Suspense } from "react";

import { ResumeUpload } from "@/components/resume-upload";
import { getSignedInSource } from "@/lib/repository";

export default function ResumePage() {
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Resume</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Upload your resume as a PDF or Word (.docx) file. Fit scores use the text extracted from your latest upload.
      </p>
      <div className="mt-6">
        <ResumeUpload />
      </div>
      <Suspense fallback={<p className="mt-8 text-sm text-muted-foreground">Loading…</p>}>
        <PrimaryResume />
      </Suspense>
    </main>
  );
}

async function PrimaryResume() {
  const { repository } = await getSignedInSource();
  const resume = await repository.getPrimaryResume();
  if (!resume) return <p className="mt-8 text-sm text-muted-foreground">No resume uploaded yet.</p>;

  return (
    <section className="mt-8">
      <h2 className="font-medium">{resume.file_name}</h2>
      <p className="text-xs text-muted-foreground">Uploaded {new Date(resume.created_at).toLocaleString()}</p>
      {resume.text ? (
        <pre className="mt-4 max-h-[32rem] overflow-auto rounded-lg border bg-muted/40 p-4 text-sm whitespace-pre-wrap">
          {resume.text}
        </pre>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">Text hasn&apos;t been extracted yet.</p>
      )}
    </section>
  );
}
