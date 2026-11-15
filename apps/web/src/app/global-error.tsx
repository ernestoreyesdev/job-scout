"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

/** Shown when the root layout itself fails; the error goes to Sentry. */
export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  // Sends the error to Sentry, outside React.
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="p-8 font-sans">
        <h1 className="text-lg font-semibold">Something went wrong.</h1>
        <p className="mt-2 text-sm">Reload the page to try again.</p>
      </body>
    </html>
  );
}
