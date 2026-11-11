import { describe, expect, it } from "vitest";

import type { AgentRunRow } from "@/lib/db";
import { describeRun } from "@/lib/runs";

function run(kind: string, input: Record<string, unknown>): AgentRunRow {
  return {
    id: "run-1",
    user_id: "user-1",
    kind,
    input,
    status: "done",
    error: null,
    error_code: null,
    progress: null,
    usage: null,
    timings: null,
    jobs_added: null,
    created_at: "2026-11-11T00:00:00Z",
    updated_at: "2026-11-11T00:00:00Z",
    finished_at: null,
  };
}

describe("describeRun", () => {
  it("spells out a search's rule in plain words", () => {
    const { title, detail } = describeRun(
      run("search", {
        keywords: ["software engineer", "ai engineer"],
        workplace_types: ["onsite", "hybrid", "remote"],
        location: "Tampa",
        limit: 10,
        score: true,
        min_score: 70,
      }),
    );

    expect(title).toBe("All companies");
    expect(detail).toBe(" · software engineer, ai engineer · On-site, hybrid or remote · Tampa · up to 10 jobs · score 70+");
  });

  it("names the company and one job", () => {
    expect(describeRun(run("search", { keywords: ["engineer"], company: "Acme", limit: 1 }))).toEqual({
      title: "Acme",
      detail: " · engineer · up to 1 job",
    });
  });

  it("describes re-scores and imports", () => {
    expect(describeRun(run("rescore", {})).title).toBe("Re-score with current resume");
    expect(describeRun(run("import", { entries: ["a", "b"] }))).toEqual({ title: "Import companies", detail: " (2 entries)" });
  });
});
