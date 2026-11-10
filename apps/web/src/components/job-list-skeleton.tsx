const CARDS = 3;

/** Placeholder toolbar and job cards shown while a job list loads. */
export function JobListSkeleton() {
  return (
    <div className="mt-8 animate-pulse" aria-busy="true" aria-label="Loading jobs">
      <div className="h-14 rounded-xl border bg-card" />
      <ul className="mt-3 space-y-3">
        {Array.from({ length: CARDS }, (_, i) => (
          <li key={i} className="flex gap-4 rounded-xl border bg-card p-4">
            <div className="size-11 shrink-0 rounded-full bg-muted" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-2/5 rounded bg-muted" />
              <div className="h-3 w-1/4 rounded bg-muted" />
              <div className="flex gap-1.5 pt-1">
                <div className="h-5 w-20 rounded-full bg-muted" />
                <div className="h-5 w-14 rounded-full bg-muted" />
                <div className="h-5 w-16 rounded-full bg-muted" />
              </div>
              <div className="h-3 w-full rounded bg-muted" />
              <div className="h-3 w-4/5 rounded bg-muted" />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
