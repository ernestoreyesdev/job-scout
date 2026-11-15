/** Short forms written out before titles are compared, as the agent's TITLE_ABBREVIATIONS does. */
const TITLE_ABBREVIATIONS: Record<string, string> = { sr: "senior", jr: "junior", eng: "engineer", engr: "engineer" };

/**
 * A job as the agent's `job_key` compares it across sources: the company in letters and digits, and the title's words
 * with short forms written out ('Sr' reads as 'Senior').
 */
export function jobKey(company: string, title: string): string {
  const name = company.toLowerCase().replace(/[^a-z0-9]/g, "");
  const words = title.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return `${name}|${words.map((word) => TITLE_ABBREVIATIONS[word] ?? word).join(" ")}`;
}
