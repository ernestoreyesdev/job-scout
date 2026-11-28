import { createClient } from "./supabase/server";

/**
 * Calls the Python agent from the server, forwarding the user's Supabase
 * access token so the agent can verify it and query under RLS.
 */
export async function callAgent<T>(path: string, init: { method: string; body?: unknown }): Promise<T> {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) throw new Error("AGENT_URL is not configured.");

  const supabase = await createClient();
  const session = supabase ? (await supabase.auth.getSession()).data.session : null;
  if (!session) throw new Error("Not signed in.");

  let response: Response;
  try {
    response = await fetch(`${agentUrl}${path}`, {
      method: init.method,
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
    });
  } catch {
    throw new Error("The agent service is not reachable.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => undefined);
    throw agentError(response.status, body);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** The code the agent sends when it can't find a job from its link. */
export const JOB_LINK_UNREADABLE = "job_link_unreadable";

/** An error response from the agent, with its HTTP status and the code it sent, if any. */
export class AgentError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null = null,
  ) {
    super(message);
  }
}

/**
 * The AgentError for an error response's status and body: its message, or the
 * first field that failed the agent's checks, and its code when it sent one.
 */
export function agentError(status: number, body: unknown): AgentError {
  const { detail, code } = (body ?? {}) as { detail?: unknown; code?: unknown };
  const [problem] = Array.isArray(detail) ? (detail as { loc?: unknown[]; msg?: unknown }[]) : [];
  const field = problem?.loc?.at(-1);
  const message =
    typeof detail === "string"
      ? detail
      : typeof problem?.msg === "string"
        ? `${typeof field === "string" ? `${field}: ` : ""}${problem.msg}`
        : `Agent request failed (${status}).`;
  return new AgentError(message, status, typeof code === "string" ? code : null);
}
