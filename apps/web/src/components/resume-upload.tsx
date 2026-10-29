"use client";

import { useRef, useState, useTransition } from "react";

import { uploadResume } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Uploads a PDF or .docx as the new primary resume, then asks the agent to extract its text. */
export function ResumeUpload() {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  function upload(formData: FormData) {
    startTransition(async () => {
      const result = await uploadResume(formData);
      setError(result.ok ? null : (result.error ?? "Could not upload the resume."));
      if (result.ok) formRef.current?.reset();
    });
  }

  return (
    <form ref={formRef} action={upload} className="space-y-2">
      <div className="flex gap-2">
        <Input
          name="file"
          type="file"
          required
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        />
        <Button type="submit" disabled={pending}>
          {pending ? "Uploading…" : "Upload"}
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  );
}
