import * as Sentry from "@sentry/nextjs";

// Reports browser errors to Sentry; without NEXT_PUBLIC_SENTRY_DSN the SDK stays off.
Sentry.init({ dsn: process.env.NEXT_PUBLIC_SENTRY_DSN });
