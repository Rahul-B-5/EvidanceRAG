# EvidenceRAG product strategy

EvidenceRAG serves researchers who already have a collection of papers and need
to establish what those papers support. The most valuable interaction is moving
from a claim or value to the exact passage, understanding its conditions, and
carrying that provenance into a note, experiment, or report.

## Product references

- Elicit organizes systematic review around screening and extraction columns.
  Gemini Notebook links answers to source excerpts. SciSpace brings PDF reading
  and literature review into one workspace. [Elicit](https://support.elicit.com/en/articles/14759154-systematic-reviews-in-elicit),
  [Gemini Notebook](https://support.google.com/gemininotebook/answer/16179559),
  [SciSpace](https://scispace.com/).
- ResearchRabbit and Litmaps emphasize citation-network discovery and
  exploration. Connected Papers emphasizes discovering neighboring papers;
  its about page could not be inspected without running its client. [ResearchRabbit](https://learn.researchrabbit.ai/en/articles/17309356-how-to-read-the-citation-map-in-researchrabbit),
  [Litmaps](https://www.litmaps.com/),
  [Connected Papers](https://www.connectedpapers.com/about).
- Zotero links annotations to PDF pages. Reader exports highlights and notes.
  Obsidian surfaces relationships through backlinks. Linear and Raycast
  provide models for fast keyboard navigation. [Zotero](https://www.zotero.org/support/pdf_reader),
  [Readwise](https://docs.readwise.io/reader/docs/faqs/exporting),
  [Obsidian](https://obsidian.md/help/plugins/backlinks),
  [Linear](https://linear.app/docs/keyboard-shortcuts),
  [Raycast](https://manual.raycast.com/).

## Design commitments

1. **Provenance at every handoff.** Use stable indexed excerpt references for
   individual findings. Carry paper, pages and passage IDs from the matrix to
   the reader, notebook, graph and reports. Expose interpretation and evidence
   support as separately reviewable information.
2. **Conditions before rankings.** Put missing protocols, differing datasets,
   baselines and metric units alongside values. Offer candidate agreement and
   disagreement for review when the source conditions align.
3. **A graph of the evidence inside papers.** Build graph neighborhoods from
   typed, inspectable source relationships. Start with the comparison and
   expand to the workspace as claims gain durable IDs.
4. **A useful local workflow.** Keep library, reading, retrieval and evidence
   packets usable without a generation service. Make cloud submission explicit
   in provider settings. Keep exports editable and portable.

The main friction addressed here is the handoff among reading, comparing,
recording and writing. Showing more rows or links does little if a researcher
must re-open each paper and reconstruct why a claim or evaluation was included.
