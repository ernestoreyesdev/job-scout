import { describe, expect, it } from "vitest";

import { jobListHref, parseJobQuery } from "@/lib/job-query";

describe("parseJobQuery", () => {
  it("reads every known setting and keeps them for links", () => {
    const query = parseJobQuery({
      view: "rated",
      sort: "posted",
      status: "applied",
      company: "Acme",
      open: "1",
      noclearance: "1",
      salary: "120000.4",
      page: "3",
    });

    expect(query.rated).toBe(true);
    expect(query.sort).toBe("posted");
    expect(query.filters).toEqual({ status: "applied", company: "Acme", hideClosed: true, hideClearance: true, minSalary: 120000 });
    expect(query.page).toBe(3);
    expect(query.params).toEqual({
      view: "rated",
      sort: "posted",
      status: "applied",
      company: "Acme",
      open: "1",
      noclearance: "1",
      salary: "120000",
    });
  });

  it("ignores unknown values and leaves the default sort out of links", () => {
    const query = parseJobQuery({ sort: "random", status: "hired", salary: "-5", page: "x", view: "all" }, "desc");

    expect(query.sort).toBe("desc");
    expect(query.rated).toBe(false);
    expect(query.filters.status).toBeUndefined();
    expect(query.filters.minSalary).toBeUndefined();
    expect(query.page).toBe(1);
    expect(query.params).toEqual({});
  });

  it("takes the first value of a repeated setting", () => {
    expect(parseJobQuery({ company: ["Acme", "Beta"] }).filters.company).toBe("Acme");
  });
});

describe("jobListHref", () => {
  it("leaves out empty settings", () => {
    expect(jobListHref("/jobs", { view: "rated", company: "" })).toBe("/jobs?view=rated");
    expect(jobListHref("/jobs", {})).toBe("/jobs");
  });
});
