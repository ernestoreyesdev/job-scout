"use client";

import { FileUp } from "lucide-react";
import { useRef, useState, useTransition } from "react";

import { uploadResume } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Uploads a PDF or .docx as the new primary resume, then asks the agent to extract its text. A file can be dropped
 * on the card or picked from it; Upload appears once one is chosen.
 */
export function ResumeUpload() {
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

  function drop(event: React.DragEvent) {
    event.preventDefault();
    setDragging(false);
    const files = event.dataTransfer.files;
    if (!files.length || !inputRef.current) return;
    inputRef.current.files = files;
    setFileName(files[0].name);
  }

  return (
    <form ref={formRef} action={upload} className="space-y-3">
      <label
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors hover:border-foreground/30",
          dragging && "border-primary bg-primary/5",
        )}
      >
        <FileUp className="size-6 text-muted-foreground" />
        <span className="font-medium">{fileName ?? "Drop your resume here, or choose a file"}</span>
        <span className="text-sm text-muted-foreground">PDF or Word (.docx), up to 1 MB</span>
        <input
          ref={inputRef}
          name="file"
          type="file"
          required
          className="sr-only"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => setFileName(event.target.files?.[0]?.name ?? null)}
        />
      </label>
      {fileName && (
        <div className="flex justify-end">
          <Button type="submit" disabled={pending}>
            {pending ? "Uploading…" : "Upload"}
          </Button>
        </div>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </form>
  );
}
