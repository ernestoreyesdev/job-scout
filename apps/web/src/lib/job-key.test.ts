import { describe, expect, it } from "vitest";

import { jobKey } from "@/lib/job-key";

describe("jobKey", () => {
  it("matches the same job written differently, as the agent does", () => {
    expect(jobKey("Curai", "Sr Software Engineer, Full-Stack")).toBe(jobKey("Curai", "Senior Software Engineer, Full Stack"));
    expect(jobKey("ACME", "Sr. Software Engineer, Backend")).toBe(jobKey("Acme", "Senior Software Engineer Backend"));
  });

  it("keeps different companies and titles apart", () => {
    expect(jobKey("Acme", "Senior Software Engineer")).not.toBe(jobKey("Globex", "Senior Software Engineer"));
    expect(jobKey("Acme", "Software Engineer, Payments")).not.toBe(jobKey("Acme", "Software Engineer, Backend"));
  });
});
