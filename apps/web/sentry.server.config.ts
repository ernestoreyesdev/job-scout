import * as Sentry from "@sentry/nextjs";

// Reports server errors to the web app's Sentry project; without NEXT_PUBLIC_SENTRY_DSN the SDK stays off.
Sentry.init({ dsn: process.env.NEXT_PUBLIC_SENTRY_DSN });
