import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/** Previous/next links for a paged list; `params` are kept on every link (e.g. the sort order). */
export function Pager({
  basePath,
  page,
  pageCount,
  total,
  params = {},
}: {
  basePath: string;
  page: number;
  pageCount: number;
  total: number;
  params?: Record<string, string>;
}) {
  if (pageCount <= 1) return null;

  const href = (target: number) => {
    const query = new URLSearchParams({ ...params, ...(target > 1 && { page: String(target) }) }).toString();
    return query ? `${basePath}?${query}` : basePath;
  };

  return (
    <nav className="mt-4 flex items-center justify-end gap-3 text-sm" aria-label="Pages">
      <span className="text-muted-foreground">
        Page {page} of {pageCount} · {total} total
      </span>
      {page > 1 ? (
        <Button variant="outline" size="sm" asChild>
          <Link href={href(page - 1)}>
            <ChevronLeft />
            Previous
          </Link>
        </Button>
      ) : (
        <Button variant="outline" size="sm" disabled>
          <ChevronLeft />
          Previous
        </Button>
      )}
      {page < pageCount ? (
        <Button variant="outline" size="sm" asChild>
          <Link href={href(page + 1)}>
            Next
            <ChevronRight />
          </Link>
        </Button>
      ) : (
        <Button variant="outline" size="sm" disabled>
          Next
          <ChevronRight />
        </Button>
      )}
    </nav>
  );
}
