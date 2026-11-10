import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A titled card that groups one part of a page, with an optional action at the top right. */
export function SectionCard({
  title,
  description,
  action,
  className,
  children,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("rounded-xl border bg-card p-5 text-card-foreground shadow-xs", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}
