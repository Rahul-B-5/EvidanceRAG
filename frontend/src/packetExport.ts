import type { EvidencePacket } from "./api";

export type PacketFormat = "md" | "html" | "json" | "bib";
const escape = (text: string) => text.replace(/[<>&"']/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;","'":"&#39;"}[c] ?? c));
const mime = {md:"text/markdown", html:"text/html", json:"application/json", bib:"text/plain"};

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
    return `@misc{evidencerag${item.document_id},\n${fields.join(",\n")}\n}`;
  }).join("\n\n") + "\n";
}

export function packetContents(packet: EvidencePacket, format: PacketFormat): string {
  if (format === "json") return JSON.stringify({schema_version: 1, ...packet}, null, 2) + "\n";
  if (format === "bib") return bibliography(packet);
  const refs = packet.items.map((p, i) => ({
    id: `E${i + 1}`, title: p.title, pages: `${p.page_start}–${p.page_end}`,
    citation: `Paper ${p.document_id} · Pages ${p.page_start}–${p.page_end} · Passage ${p.chunk_id}`,
    quote: p.passage, note: p.note,
  }));
  if (format === "html") {
    return `<!doctype html><html lang="en"><meta charset="utf-8"><title>${escape(packet.title)}</title><body>
<main><h1>${escape(packet.title)}</h1><p>${escape(packet.question)}</p>
<h2>Briefing draft</h2><div style="white-space:pre-wrap">${escape(packet.narrative)}</div>
<h2>Source snapshots</h2>${refs.map(p => `<section id="${p.id}"><h3>[${p.id}] ${escape(p.title)}</h3>
<p>${p.citation}</p><blockquote style="white-space:pre-wrap">${escape(p.quote)}</blockquote>
<p style="white-space:pre-wrap">${escape(p.note)}</p></section>`).join("\n")}</main></body></html>`;
  }
  return [
    `# ${escape(packet.title.replace(/\s+/g, " "))}`, escape(packet.question), "## Briefing draft",
    packet.narrative ? escape(packet.narrative) : "No briefing drafted.",
    "## Source snapshots",
    ...refs.flatMap(p => [`### [${p.id}] ${escape(p.title.replace(/\s+/g, " "))}`, p.citation,
      p.quote.split("\n").map(line => "> " + escape(line)).join("\n"), escape(p.note)]),
  ].filter(Boolean).join("\n\n") + "\n";
}

export function downloadPacket(packet: EvidencePacket, format: PacketFormat) {
  const url = URL.createObjectURL(new Blob([packetContents(packet, format)], {type:`${mime[format]};charset=utf-8`}));
  const link = document.createElement("a");
  link.href = url; link.download = `evidencerag-packet-${packet.id.slice(0, 8)}.${format}`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
