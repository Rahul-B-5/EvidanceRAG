import {test} from "node:test";
import assert from "node:assert/strict";
import {comparisonBrief} from "../.test-build/comparisonBrief.js";

test("comparison briefing exports both exact opposing excerpts and source ranges", () => {
  const result = {
    papers:[], topics:[], checks:[],
    contradictions:[{
      conditions:{subject:"OrioleNet", baseline:"CedarNet", metric:"F1", protocol:"10-seed protocol"},
      left:{title:"Study A", quote:"OrioleNet outperformed CedarNet.", source:{document_id:1, chunk_id:21, page_start:2, page_end:2}},
      right:{title:"Study B", quote:"OrioleNet underperformed CedarNet.", source:{document_id:2, chunk_id:34, page_start:4, page_end:5}},
    }],
  };
  const brief = comparisonBrief(result, {});
  assert.match(brief, /Potential disagreements/);
  assert.match(brief, /protocol · 10-seed protocol/);
  assert.match(brief, /outperformed CedarNet\.\n\nSource: paper 1, pages 2, indexed passage 21/);
  assert.match(brief, /underperformed CedarNet\.\n\nSource: paper 2, pages 4–5, indexed passage 34/);
});
