"use client";

import { useReportWebVitals } from "next/web-vitals";

type Report = Parameters<typeof useReportWebVitals>[0];

/** Sends each page load measurement (path only, no query) to /api/vitals without delaying the page. */
const report: Report = (metric) => {
  const page = new URL(metric.navigationURL ?? window.location.href, window.location.origin).pathname;
  if (page.startsWith("/api/")) return;
  const body = JSON.stringify({
    page,
    metric: metric.name,
    value: metric.value,
    rating: metric.rating,
    navigationType: metric.navigationType,
  });
  if (navigator.sendBeacon) navigator.sendBeacon("/api/vitals", new Blob([body], { type: "application/json" }));
  else fetch("/api/vitals", { method: "POST", body, keepalive: true, headers: { "Content-Type": "application/json" } });
};

/** Reports Core Web Vitals for every page, including client-side navigations. */
export function WebVitals() {
  useReportWebVitals(report);
  return null;
}
