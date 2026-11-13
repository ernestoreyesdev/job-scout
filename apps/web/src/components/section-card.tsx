import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A titled card that groups one part of a page, with an optional action at the top right.
 * A collapsible card starts open and folds to its title when the title is clicked; its action shows only while open.
 */
export function SectionCard({
  title,
  description,
  action,
  collapsible = false,
  className,
  children,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  collapsible?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const heading = (
    <div className="min-w-0">
      <h2 className="font-semibold">{title}</h2>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </div>
  );
  const cardClass = cn("rounded-xl border bg-card p-5 text-card-foreground shadow-xs", className);

  if (collapsible) {
    return (
      <details open className={cn("group", cardClass)}>
        <summary className="flex cursor-pointer list-none items-start justify-between gap-3 [&::-webkit-details-marker]:hidden">
          {heading}
          <ChevronDown
            aria-hidden
            className="mt-0.5 size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
          />
        </summary>
        {action && <div className="mt-3 flex justify-end">{action}</div>}
        <div className="mt-4">{children}</div>
      </details>
    );
  }

  return (
    <section className={cardClass}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        {heading}
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}
