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
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) => body.detail)
      .catch(() => undefined);
    throw new Error(typeof detail === "string" ? detail : `Agent request failed (${response.status}).`);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** Asks the agent to start the daily board refresh, passing on the cron secret; returns the agent's status code. */
export async function startBoardRefresh(authorization: string): Promise<number> {
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) throw new Error("AGENT_URL is not configured.");
  const response = await fetch(`${agentUrl}/refresh`, { method: "POST", headers: { Authorization: authorization }, cache: "no-store" });
  return response.status;
}
