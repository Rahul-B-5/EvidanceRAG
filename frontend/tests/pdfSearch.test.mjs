import {test} from "node:test";
import assert from "node:assert/strict";
import {pdfSearchExcerpt} from "../.test-build/pdfSearch.js";

test("PDF search matches a phrase across line breaks and normalized ligatures", () => {
  assert.deepEqual(pdfSearchExcerpt("A ﬁnding\nuses [F1].", "FINDING uses [f1]"),
    {before:"A ", match:"finding uses [F1]", after:"."});
});

test("PDF search treats regex punctuation literally and bounds excerpts", () => {
  assert.equal(pdfSearchExcerpt("Anything", ".*"), null);
  const excerpt = pdfSearchExcerpt("x".repeat(100) + " C++ " + "y".repeat(100), "C++");
  assert.equal(excerpt.match, "C++");
  assert.ok(excerpt.before.startsWith("…"));
  assert.ok(excerpt.after.endsWith("…"));
});
