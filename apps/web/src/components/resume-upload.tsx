"use client";

import { useRef, useState, useTransition } from "react";

import { uploadResume } from "@/app/actions";
import { Button } from "@/components/ui/button";

/**
 * Uploads a PDF or .docx as the new primary resume, then asks the agent to extract its text. Upload appears once a
 * file is chosen.
 */
export function ResumeUpload() {
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  function upload(formData: FormData) {
    startTransition(async () => {
      const result = await uploadResume(formData);
      setError(result.ok ? null : (result.error ?? "Could not upload the resume."));
      if (result.ok) {
        formRef.current?.reset();
        setFileName(null);
      }
    });
  }

  return (
    <form ref={formRef} action={upload} className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button asChild variant="outline">
          <label>
            {fileName ? "Choose another file" : "Choose file"}
            <input
              name="file"
              type="file"
              required
              className="sr-only"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => setFileName(event.target.files?.[0]?.name ?? null)}
            />
          </label>
        </Button>
        {fileName && (
          <>
            <span className="min-w-0 truncate text-sm">{fileName}</span>
            <Button type="submit" disabled={pending}>
              {pending ? "Uploading…" : "Upload"}
            </Button>
          </>
        )}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  );
}
