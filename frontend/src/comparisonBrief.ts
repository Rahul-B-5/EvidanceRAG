import type { Finding, StructuredComparison } from "./api";

function plain(value: string) {
  return value.replace(/[<>&]/g, char => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[char] ?? char);
}

export function followUpExcerpts(result: StructuredComparison) {
  const signal = /\bfuture (?:work|research|stud(?:y|ies))\b|\bfurther (?:work|research|investigation|studies)\b|\bremains? (?:unexplored|unclear|an open question)\b/i;
  return result.papers.flatMap(paper => paper.findings
    .filter(f => f.topic === "limitations" && signal.test(f.quote))
    .map(finding => ({title: paper.title, finding})));
}

export function comparisonBrief(result: StructuredComparison, labels: Record<string, string>) {
  const titles = new Map(result.papers.map(p => [p.document_id, p.title]));
  const cite = (f: Finding) => {
    const s = f.source;
    const range = s.page_start === s.page_end ? String(s.page_start) : `${s.page_start}–${s.page_end}`;
    return `> ${plain(f.quote)}\n\nSource: paper ${s.document_id}, pages ${range}, indexed passage ${s.chunk_id}.`;
  };
  const lines = [
    "# EvidenceRAG comparison briefing",
    "Coverage is limited to the indexed passages reviewed for the selected papers. Review source context before ranking results.",
  ];
  for (const paper of result.papers) {
    lines.push(`## ${plain(paper.title)}`, `${paper.reviewed_passages} passages reviewed, ${paper.findings.length} verified excerpts.`);
    for (const topic of result.topics) {
      const findings = paper.findings.filter(f => f.topic === topic);
      lines.push(`### ${labels[topic] ?? topic}`, findings.length ? findings.map(cite).join("\n\n") : "No verified finding in reviewed passages.");
    }
  }
  lines.push("## Comparability checks");
  for (const check of result.checks) {
    lines.push(`### ${check.document_ids.map(id => plain(titles.get(id) ?? String(id))).join(" and ")}`);
    if (!check.outcomes.length) lines.push("A numerical finding is missing for at least one paper.");
    for (const outcome of check.outcomes) {
      lines.push(
        `**${labels[outcome.status]}**. Differences: ${outcome.differences.join(", ") || "none detected"}. Missing conditions: ${outcome.missing.join(", ") || "none detected"}.`,
        cite(outcome.left),
        cite(outcome.right),
      );
    }
  }
  lines.push("## Author-reported follow-up");
  const followUps = followUpExcerpts(result);
  if (!followUps.length) lines.push("No explicit follow-up wording matched in the verified limitation excerpts.");
  for (const {title, finding} of followUps) lines.push(`### ${plain(title)}`, cite(finding));
  return lines.join("\n\n") + "\n";
}
