"use client";

import { useReportWebVitals } from "next/web-vitals";

import { TITLE_SUFFIX } from "@/lib/titles";

type Report = Parameters<typeof useReportWebVitals>[0];

/** When the last move to another page of this site began (link click or back/forward); null once it reported ready. */
let navigationStart: number | null = null;
/** The title of the page the browser fully loaded, which every standard web vital belongs to. */
let loadedTitle: string | null = null;

if (typeof document !== "undefined") {
  document.addEventListener(
    "click",
    (event) => {
      const link = (event.target as Element | null)?.closest?.("a[href]");
      if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.origin !== window.location.origin) return;
      if (link.pathname !== window.location.pathname) navigationStart = performance.now();
    },
    true,
  );
  window.addEventListener("popstate", () => {
    navigationStart = performance.now();
  });
}

function pageTitle(): string {
  return document.title.endsWith(TITLE_SUFFIX) ? document.title.slice(0, -TITLE_SUFFIX.length) : document.title;
}

function send(page: string, metric: string, value: number, rating?: string, navigationType?: string): void {
  const body = JSON.stringify({ page, metric, value, rating, navigationType });
  if (navigator.sendBeacon) navigator.sendBeacon("/api/vitals", new Blob([body], { type: "application/json" }));
  else fetch("/api/vitals", { method: "POST", body, keepalive: true, headers: { "Content-Type": "application/json" } });
}

/** Sends each Core Web Vital under the title of the page it measured, without delaying the page. */
const report: Report = (metric) => {
  loadedTitle ??= pageTitle();
  const page = metric.navigationType === "soft-navigation" ? pageTitle() : loadedTitle;
  send(page, metric.name, metric.value, metric.rating, metric.navigationType);
};

/** Reports Core Web Vitals; browsers without soft-navigation timing only measure full page loads. */
export function WebVitals() {
  useReportWebVitals(report);
  return null;
}

/**
 * Rendered once a page's data is on screen: reports READY, the milliseconds since the move that opened the page,
 * or since the page load began when it was a full load.
 */
export function PageReady() {
  return <span hidden ref={markReady} />;
}

/** A stable ref callback, so React runs it once when the marker mounts rather than on every re-render. */
function markReady(element: HTMLSpanElement | null): void {
  if (!element) return;
  const start = navigationStart ?? 0;
  navigationStart = null;
  requestAnimationFrame(() => send(pageTitle(), "READY", performance.now() - start, undefined, start ? "navigate" : "load"));
}
