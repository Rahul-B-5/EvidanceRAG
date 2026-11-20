import {test} from "node:test";
import assert from "node:assert/strict";
import {reproductionMarkdown} from "../.test-build/reproductionDossier.js";

test("reproduction export separates missing components from explicit limitations and cites both sides", () => {
  const source = {document_id:2, chunk_id:99, page_start:3, page_end:4};
  const dossier = {document_id:2, title:"Study", items:[{
    label:"Code and artifacts", status:"mention", verify:"Review the artifact release.",
    disclosures:[
      {label:"Code availability", status:"mixed", evidence:[
        {kind:"reported", excerpt:"The code is publicly available at the project website.", source},
        {kind:"limitation", excerpt:"The implementation is available only upon request.", source:{...source, chunk_id:100}},
      ]},
      {label:"Version pin", status:"not_located", evidence:[]},
    ],
  }]};
  const markdown = reproductionMarkdown(dossier, "Check the supplement.");
  assert.match(markdown, /Code availability\n\nDifferent statements to review/);
  assert.match(markdown, /Limitation wording\n\n> The implementation is available only upon request/);
  assert.match(markdown, /pages 3–4 · passage 100/);
  assert.match(markdown, /Version pin\n\nNot located/);
  assert.match(markdown, /Researcher notes\n\nCheck the supplement/);
});
