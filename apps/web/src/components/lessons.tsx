"use client";

import { RefreshCw, X } from "lucide-react";
import { useState } from "react";

import { addLesson, deleteLesson, refreshLessons } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MAX_LESSON_LENGTH, type LessonRow } from "@/lib/db";
import { useAction } from "@/lib/use-action";

/** The user's lessons, each deletable, with a box to write one and a button to learn them again now. */
export function Lessons({ lessons }: { lessons: LessonRow[] }) {
  const { run, pending, error } = useAction();
  const [draft, setDraft] = useState("");

  function add(formData: FormData) {
    run(() => addLesson(formData), "Could not add the lesson.", (result) => {
      if (result.ok) setDraft("");
    });
  }

  return (
    <div className="space-y-4">
      {lessons.length ? (
        <ul className="divide-y rounded-lg border">
          {lessons.map((lesson) => (
            <li key={lesson.id} className="flex items-start justify-between gap-3 px-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm">{lesson.text}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {lesson.source === "user"
                    ? "Written by you"
                    : `Learned from ${lesson.evidence} ${lesson.evidence === 1 ? "job" : "jobs"} · confirmed ${lesson.confirmed_at.slice(0, 10)}`}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete lesson: ${lesson.text}`}
                disabled={pending}
                onClick={() => run(() => deleteLesson(lesson.id), "Could not delete the lesson.")}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          Nothing yet. Lessons appear once you&apos;ve rated or applied to a few jobs.
        </p>
      )}
      <form action={add} className="flex flex-wrap gap-2">
        <Input
          name="lesson"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={MAX_LESSON_LENGTH}
          required
          aria-label="Your own lesson"
          placeholder="Add your own, such as “No jobs that need a security clearance”"
          className="min-w-64 flex-1"
        />
        <Button type="submit" disabled={pending}>
          Add
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={pending}
          onClick={() => run(refreshLessons, "Could not update the lessons.")}
        >
          <RefreshCw />
          Update now
        </Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
