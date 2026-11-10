import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";

import { AdminNavLink } from "@/components/admin-nav-link";
import { NavLinks } from "@/components/nav-links";
import { ThemeSync } from "@/components/theme-sync";
import { UserMenu } from "@/components/user-menu";
import { WebVitals } from "@/components/web-vitals";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";

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

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <Suspense>
          <ThemeSync />
        </Suspense>
        <header className="border-b">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
            <NavLinks
              extra={
                <Suspense>
                  <AdminNavLink />
                </Suspense>
              }
            />
            <Suspense>
              <UserMenu />
            </Suspense>
          </div>
        </header>
        {children}
        <WebVitals />
      </body>
    </html>
  );
}
