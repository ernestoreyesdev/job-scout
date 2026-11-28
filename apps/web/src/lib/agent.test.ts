import { describe, expect, it } from "vitest";

import { agentError, JOB_LINK_UNREADABLE } from "@/lib/agent";

describe("agentError", () => {
  it("keeps the message and the code the agent sent", () => {
    const error = agentError(422, { detail: "Couldn't find this job from its link.", code: JOB_LINK_UNREADABLE });

    expect([error.message, error.status, error.code]).toEqual(["Couldn't find this job from its link.", 422, JOB_LINK_UNREADABLE]);
  });

  it("reads a failed field check as its field and problem, without a code", () => {
    const body = { detail: [{ loc: ["body", "title"], msg: "String should have at most 300 characters", type: "string_too_long" }] };

    const error = agentError(422, body);

    expect([error.message, error.code]).toEqual(["title: String should have at most 300 characters", null]);
  });

  it("falls back to the status when the body says nothing", () => {
    expect(agentError(502, undefined).message).toBe("Agent request failed (502).");
  });
});
