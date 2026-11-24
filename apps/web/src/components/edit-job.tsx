"use client";

import { useState, type FormEvent } from "react";

import { editJob, loadJobText, type JobTextResult } from "@/app/actions";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAction } from "@/lib/use-action";

type JobText = NonNullable<JobTextResult["text"]>;

const FIELDS = ["title", "company", "description"] as const;

/** Edit button that opens a dialog to correct a saved job's title, company and description. */
export function EditJob({ id }: { id: string }) {
  const [shown, setShown] = useState<JobText | null>(null);
  const { run, pending, error } = useAction();

  function open() {
    run(() => loadJobText(id), "Could not load this job.", (result) => setShown(result.text ?? null));
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    if (FIELDS.every((field) => String(formData.get(field)).trim() === shown?.[field].trim())) {
      setShown(null);
      return;
    }
    run(() => editJob(id, formData), "Could not save.", (result) => result.ok && setShown(null));
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={open} disabled={pending}>
        {pending && !shown ? "Loading…" : "Edit"}
      </Button>
      {error && !shown && <p className="basis-full text-sm text-destructive">{error}</p>}
      <AlertDialog open={shown !== null} onOpenChange={(next) => !pending && !next && setShown(null)}>
        <AlertDialogContent className="data-[size=default]:max-w-[calc(100%-2rem)] data-[size=default]:sm:max-w-xl">
          <form onSubmit={save} className="grid gap-4">
            <AlertDialogHeader>
              <AlertDialogTitle>Edit job</AlertDialogTitle>
              <AlertDialogDescription>
                Your changes show only for you and are used to score this job. Leave a field blank to go back to the
                original.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="grid gap-1.5">
              <Label htmlFor={`${id}-title`}>Title</Label>
              <Input id={`${id}-title`} name="title" defaultValue={shown?.title} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${id}-company`}>Company</Label>
              <Input id={`${id}-company`} name="company" defaultValue={shown?.company} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${id}-description`}>Description</Label>
              <Textarea id={`${id}-description`} name="description" rows={10} defaultValue={shown?.description} className="max-h-[50vh]" />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <AlertDialogFooter>
              <AlertDialogCancel type="button" disabled={pending}>
                Cancel
              </AlertDialogCancel>
              <Button type="submit" disabled={pending}>
                {pending ? "Saving…" : "Save"}
              </Button>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
