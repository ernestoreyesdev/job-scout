"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/tracker", label: "Tracker" },
  { href: "/jobs", label: "Jobs" },
  { href: "/companies", label: "Companies" },
  { href: "/insights", label: "Insights" },
  { href: "/resume", label: "Resume" },
  { href: "/settings", label: "Settings" },
];

/** The app's pages plus any `extra` items, with the current one highlighted; scrolls sideways on narrow screens. */
export function NavLinks({ extra }: { extra?: ReactNode }) {
  return (
    <nav className="-mx-2 flex min-w-0 items-center gap-1 overflow-x-auto text-sm">
      <Link href="/tracker" className="shrink-0 px-2 font-semibold tracking-tight">
        Job Finder
      </Link>
      {NAV.map((item) => (
        <NavItem key={item.href} href={item.href} label={item.label} />
      ))}
      {extra}
    </nav>
  );
}

/** One nav link, highlighted while its page or one under it is open. */
export function NavItem({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const current = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        "shrink-0 rounded-full px-3 py-1 text-muted-foreground transition-colors hover:text-foreground",
        current && "bg-muted font-medium text-foreground",
      )}
    >
      {label}
    </Link>
  );
}
