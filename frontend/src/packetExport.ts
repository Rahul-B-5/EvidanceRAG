import type { EvidencePacket } from "./api";

export type PacketFormat = "md" | "html" | "json" | "bib";
const escape = (text: string) => text.replace(/[<>&"']/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;","'":"&#39;"}[c] ?? c));
const mime = {md:"text/markdown", html:"text/html", json:"application/json", bib:"text/plain"};

export function packetCitationStatus(narrative: string, itemCount: number) {
  const labels = [...new Set(Array.from(narrative.matchAll(/\[(E[0-9]+)\]/g), match => match[1]))];
  const available = new Set(Array.from({length:itemCount}, (_, index) => `E${index + 1}`));
  return {cited:labels.filter(label => available.has(label)), unknown:labels.filter(label => !available.has(label))};
}

function bibliography(packet: EvidencePacket) {
  const documents = new Map(packet.items.map(item => [item.document_id, item]));
  const clean = (v: string) => v.replace(/[\n\r]+/g, " ").replace(/[\\{}%&#_$^~]/g, c => ({
    "\\":"\\textbackslash{}", "{":"\\{", "}":"\\}", "%":"\\%", "&":"\\&", "#":"\\#",
    "_":"\\_", "$":"\\$", "^":"\\textasciicircum{}", "~":"\\textasciitilde{}",
  }[c] ?? c));
  return Array.from(documents.values(), item => {
    const fields = [`  title = {${clean(item.title)}}`];
    if (item.authors.length) fields.push(`  author = {${item.authors.map(clean).join(" and ")}}`);
    if (item.publication_year) fields.push(`  year = {${item.publication_year}}`);
    if (item.doi) fields.push(`  doi = {${clean(item.doi)}}`);
    if (item.venue) fields.push(`  howpublished = {${clean(item.venue)}}`);
    return `@misc{evidencerag${item.document_id},\n${fields.join(",\n")}\n}`;
  }).join("\n\n") + "\n";
}

export function packetContents(packet: EvidencePacket, format: PacketFormat, templateName?: string): string {
  if (format === "json") return JSON.stringify({schema_version: 1, ...packet}, null, 2) + "\n";
  if (format === "bib") return bibliography(packet);
  const refs = packet.items.map((p, i) => ({
    id: `E${i + 1}`, title: p.title, pages: `${p.page_start}–${p.page_end}`,
    citation: `Paper ${p.document_id} · Pages ${p.page_start}–${p.page_end} · Passage ${p.chunk_id}`,
    quote: p.passage, note: p.note,
  }));
  if (format === "html") {
    const valid = new Set(refs.map(item => item.id));
    const narrative = escape(packet.narrative).replace(/\[(E[0-9]+)\]/g,
      (token, id: string) => valid.has(id) ? `<a href="#${id}">${token}</a>` : token);
    return `<!doctype html><html lang="en"><meta charset="utf-8"><title>${escape(packet.title)}</title><body>
<main><h1>${escape(packet.title)}</h1><p>${escape(packet.question)}</p>${templateName ? `<p>${escape(templateName)}</p>` : ""}
<h2>Briefing draft</h2><div style="white-space:pre-wrap">${narrative}</div>
<h2>Source snapshots</h2>${refs.map(p => `<section id="${p.id}"><h3>[${p.id}] ${escape(p.title)}</h3>
<p>${p.citation}</p><blockquote style="white-space:pre-wrap">${escape(p.quote)}</blockquote>
<p style="white-space:pre-wrap">${escape(p.note)}</p></section>`).join("\n")}</main></body></html>`;
  }
  return [
    `# ${escape(packet.title.replace(/\s+/g, " "))}`, escape(packet.question),
    templateName ? `Template · ${escape(templateName)}` : "", "## Briefing draft",
    packet.narrative ? escape(packet.narrative) : "No briefing drafted.",
    "## Source snapshots",
    ...refs.flatMap(p => [`### [${p.id}] ${escape(p.title.replace(/\s+/g, " "))}`, p.citation,
      p.quote.split("\n").map(line => "> " + escape(line)).join("\n"), escape(p.note)]),
  ].filter(Boolean).join("\n\n") + "\n";
}

export function downloadPacket(packet: EvidencePacket, format: PacketFormat, templateName?: string) {
  const url = URL.createObjectURL(new Blob([packetContents(packet, format, templateName)], {type:`${mime[format]};charset=utf-8`}));
  const link = document.createElement("a");
  link.href = url; link.download = `evidencerag-packet-${packet.id.slice(0, 8)}.${format}`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
