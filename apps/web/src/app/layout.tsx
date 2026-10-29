import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";

import { UserMenu } from "@/components/user-menu";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Job Finder",
  description: "Find jobs that match your resume, score the fit and track your applications.",
};

const NAV = [
  { href: "/tracker", label: "Tracker" },
  { href: "/jobs", label: "Jobs" },
  { href: "/companies", label: "Companies" },
  { href: "/resume", label: "Resume" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <header className="border-b">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-3">
            <nav className="flex items-center gap-5 text-sm">
              <Link href="/tracker" className="font-semibold tracking-tight">
                Job Finder
              </Link>
              {NAV.map((item) => (
                <Link key={item.href} href={item.href} className="text-muted-foreground hover:text-foreground">
                  {item.label}
                </Link>
              ))}
            </nav>
            <Suspense>
              <UserMenu />
            </Suspense>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
