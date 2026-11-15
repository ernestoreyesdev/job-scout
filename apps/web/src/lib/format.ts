/** Whole percents: "42%". */
export const PERCENT = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });

/** ISO days in local time, which Swedish formatting gives: "2026-11-10". */
export const ISO_DAY = new Intl.DateTimeFormat("sv-SE", { year: "numeric", month: "2-digit", day: "2-digit" });
