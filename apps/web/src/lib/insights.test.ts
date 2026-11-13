import { describe, expect, it } from "vitest";

import { accuracyByCut, funnel, runCost, statsBySource, summarizeCosts } from "@/lib/insights";

describe("accuracyByCut", () => {
  it("counts each marked job against every cut and skips unmarked or unscored ones", () => {
    const rows = accuracyByCut([
      { fit_score: 85, fit_label: "good" },
      { fit_score: 72, fit_label: "good" },
      { fit_score: 65, fit_label: "bad" },
      { fit_score: 40, fit_label: "good" },
      { fit_score: 90, fit_label: null },
      { fit_score: null, fit_label: "bad" },
    ]);

    const at70 = rows.find((row) => row.cut === 70)!;
    expect(at70).toMatchObject({ truePositives: 2, falsePositives: 0, falseNegatives: 1, precision: 1, recall: 2 / 3 });
    const at50 = rows.find((row) => row.cut === 50)!;
    expect(at50.precision).toBeCloseTo(2 / 3);
  });

  it("has no precision when nothing reaches the cut", () => {
    expect(accuracyByCut([{ fit_score: 40, fit_label: "bad" }]).find((row) => row.cut === 80)!.precision).toBeNull();
  });
});

describe("statsBySource", () => {
  it("groups by source, busiest first", () => {
    const stats = statsBySource([
      { source: "lever", fit_score: 60, fit_label: "good", status: "saved" },
      { source: "greenhouse", fit_score: 80, fit_label: null, status: "new" },
      { source: "greenhouse", fit_score: null, fit_label: "bad", status: "new" },
    ]);

    expect(stats.map((row) => row.source)).toEqual(["greenhouse", "lever"]);
    expect(stats[0]).toMatchObject({ scored: 2, averageScore: 80, good: 0, bad: 1, pastNew: 0 });
    expect(stats[1]).toMatchObject({ scored: 1, good: 1, pastNew: 1 });
  });
});

describe("costs", () => {
  const usage = {
    input_tokens: 1_000_000,
    output_tokens: 1_000_000,
    cache_read_input_tokens: 0,
    cache_creation_input_tokens: 0,
    web_search_requests: 2,
  };

  it("prices tokens and web searches", () => {
    expect(runCost(usage)).toBeCloseTo(0.1 + 0.5 + 0.02);
    expect(runCost(null)).toBe(0);
  });

  it("averages finished searches and sums this month", () => {
    const summary = summarizeCosts(
      [
        { kind: "search", status: "done", usage, created_at: "2026-11-05T00:00:00Z" },
        { kind: "search", status: "failed", usage, created_at: "2026-10-20T00:00:00Z" },
        { kind: "rescore", status: "done", usage, created_at: "2026-11-06T00:00:00Z" },
      ],
      new Date("2026-11-10T12:00:00"),
    );

    expect(summary.runs).toBe(3);
    expect(summary.perSearch).toBeCloseTo(0.62);
    expect(summary.thisMonth).toBeCloseTo(1.24);
  });
});

describe("funnel", () => {
  it("counts every stage up to the furthest one reached", () => {
    const [row] = funnel([
      { statuses: ["new", "applied", "interviewing", "rejected"], source: "lever", resume: "a", addedBy: "search" },
      { statuses: ["applied"], source: "lever", resume: "a", addedBy: "search" },
      { statuses: ["saved"], source: "lever", resume: "a", addedBy: "search" },
    ]);

    expect(row.reached).toEqual({ applied: 2, interviewing: 1, offer: 0 });
    expect(row.responseRate).toBe(0.5);
  });

  it("leaves out groups with no applications", () => {
    const rows = funnel(
      [
        { statuses: ["applied"], source: "lever", resume: "a", addedBy: "search" },
        { statuses: ["saved"], source: "ashby", resume: "a", addedBy: "search" },
      ],
      (job) => job.source,
    );

    expect(rows.map((row) => row.label)).toEqual(["lever"]);
  });

  it("groups jobs by who added them", () => {
    const rows = funnel(
      [
        { statuses: ["applied", "interviewing"], source: "ashby", resume: "a", addedBy: "user" },
        { statuses: ["applied"], source: "manual", resume: "a", addedBy: "user" },
        { statuses: ["applied"], source: "lever", resume: "a", addedBy: "search" },
      ],
      (job) => job.addedBy,
    );

    expect(rows.map((row) => [row.label, row.reached.applied, row.responseRate])).toEqual([
      ["user", 2, 0.5],
      ["search", 1, 0],
    ]);
  });
});
