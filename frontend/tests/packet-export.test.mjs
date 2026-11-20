import assert from "node:assert/strict";
import test from "node:test";
import { packetCitationStatus, packetContents } from "../.test-build/packetExport.js";
const packet = {
  id: "fixture", title: "<script>unsafe</script>", question: "What changed?",
  narrative: "The result changed [E1].", revision: 2,
  items: [
    {chunk_id: 17, document_id: 4, title: "Paper & methods", page_start: 2, page_end: 3,
      passage: 'Source text\n<script>alert("unsafe")</script>', note: "Compare & verify.", authors: ["Doe, Alex"], publication_year: 2025},
    {chunk_id: 18, document_id: 4, title: "Paper & methods", page_start: 4, page_end: 4,
      passage: "A second excerpt", note: "", authors: ["Doe, Alex"], publication_year: 2025},
  ],
};

test("HTML export escapes researcher and source text", () => {
  const html = packetContents(packet, "html");
  assert.doesNotMatch(html, /<script>/i);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /id="E1"/);
  assert.match(html, /<a href="#E1">\[E1\]<\/a>/);
});

test("packet citation checks count unique sources and keep unknown labels visible", () => {
  assert.deepEqual(packetCitationStatus("Compare [E1] [E1] [E2] [E3] [E01].", 2),
    {cited:["E1","E2"],unknown:["E3","E01"]});
  assert.match(packetContents(packet, "md", "Research-gap brief"), /Template · Research-gap brief/);
  assert.doesNotMatch(packetContents({...packet, narrative:"Unknown [E3]"}, "html"), /href="#E3"/);
});

test("Markdown and structured exports preserve citation order and pages", () => {
  const data = JSON.parse(packetContents(packet, "json"));
  assert.equal(data.schema_version, 1);
  assert.deepEqual(data.items.map(p => p.chunk_id), [17, 18]);
  assert.match(packetContents(packet, "md"), /\[E1\].*?Pages 2–3 · Passage 17/s);
});

test("BibTeX contains one entry per paper with only known bibliographic fields", () => {
  const bibliography = packetContents(packet, "bib");
  assert.equal(bibliography.match(/@misc/g).length, 1);
  assert.match(bibliography, /author = \{Doe, Alex\}/);
  assert.match(bibliography, /year = \{2025\}/);
  assert.doesNotMatch(bibliography, /journal =|doi =/);
});
