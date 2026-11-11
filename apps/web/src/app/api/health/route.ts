import { connection } from "next/server";

/** Answers 200 when the web app is up and can reach the agent, 503 otherwise; used by the post-deploy smoke test. */
export async function GET() {
  await connection();
  const agentUrl = process.env.AGENT_URL;
  if (!agentUrl) return Response.json({ web: "ok", agent: "not configured" }, { status: 503 });
  const agent = await fetch(`${agentUrl}/health`, { cache: "no-store" })
    .then((response) => (response.ok ? "ok" : `status ${response.status}`))
    .catch(() => "unreachable");
  return Response.json({ web: "ok", agent }, { status: agent === "ok" ? 200 : 503 });
}
