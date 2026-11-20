import type { DisclosureCheck, DisclosureEvidence, Provenance, ReproductionDossier } from "./api";

export const categoryLabels = {
  specific_detail: "Specific wording located",
  mention: "General mention located",
  not_located: "Not located in reviewed passages",
};
export const disclosureLabels: Record<DisclosureCheck["status"], string> = {
  reported:"Detail reported",
  limitation:"Stated limitation",
  mixed:"Different statements to review",
  not_located:"Not located",
};
export const evidenceLabels: Record<DisclosureEvidence["kind"], string> = {
  reported:"Reported detail", limitation:"Limitation wording",
};

function clean(text: string) {
  return text.replace(/[<>&]/g, char => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[char] ?? char);
}

function cite(excerpt: string, source: Provenance) {
  return [
    `> ${clean(excerpt)}`,
    `Paper ${source.document_id} · pages ${source.page_start}–${source.page_end} · passage ${source.chunk_id}`,
  ];
}

export function reproductionMarkdown(dossier: ReproductionDossier, notes: string) {
  const sections = [
    "# Reproduction Dossier",
    `## ${clean(dossier.title.replace(/\s+/g, " "))}`,
    "Targeted scan of ranked passages. Check original pages and supplementary material before reproducing the study.",
  ];
  for (const item of dossier.items) {
    const checks = item.disclosures ?? [];
    sections.push(`### ${item.label}`, categoryLabels[item.status]);
    if (item.excerpt && item.source && !checks.some(check => check.evidence.length)) {
      sections.push(...cite(item.excerpt, item.source));
    }
    for (const check of checks) {
      sections.push(`#### ${check.label}`, disclosureLabels[check.status]);
      for (const hit of check.evidence) sections.push(evidenceLabels[hit.kind], ...cite(hit.excerpt, hit.source));
    }
    sections.push(`Verify: ${item.verify}`);
  }
  if (notes.trim()) sections.push("## Researcher notes", clean(notes));
  return sections.join("\n\n") + "\n";
}
