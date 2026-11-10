"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/tracker", label: "Tracker" },
  { href: "/jobs", label: "Jobs" },
  { href: "/companies", label: "Companies" },
  { href: "/insights", label: "Insights" },
  { href: "/resume", label: "Resume" },
  { href: "/settings", label: "Settings" },
];

/** The app's pages, with the current one highlighted; scrolls sideways on narrow screens. */
export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="-mx-2 flex min-w-0 items-center gap-1 overflow-x-auto text-sm">
      <Link href="/tracker" className="shrink-0 px-2 font-semibold tracking-tight">
        Job Finder
      </Link>
      {NAV.map((item) => {
        const current = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "shrink-0 rounded-full px-3 py-1 text-muted-foreground transition-colors hover:text-foreground",
              current && "bg-muted font-medium text-foreground",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
