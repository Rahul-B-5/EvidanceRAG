# EvidenceRAG progress

## Verified

- Repository uses `main` and pushes to `Rahul-B-5/EvidanceRAG`. See `git log` and `git ls-remote --heads origin main` for current delivery status.
- Local PostgreSQL with pgvector uses configured port 5433. Existing library has two papers and 34 indexed passages. Earlier smoke tests verified PDF import, duplicate detection, search, download and disposal of synthetic test records. Existing legacy papers still need byte-identical reimport to restore the original PDF links.
- React has dedicated light and dark themes, a searchable keyboard command palette, a sortable library and a reader with page controls, an adjustable split and indexed passages. Browser verification covered theme switching, Ctrl/⌘K selection, Reader navigation, and rendering a synthetic original PDF.
- Search, comparison and answers support workspace scope in a single-user app. Browser verification covered search, two-paper comparison and reloading a scoped conversation.
- Conversations persist with fixed scope, bounded history and atomic message pairs. Integration tests cover retry after failed persistence and scoped retrieval.
- Gemini, OpenAI-compatible Chat Completions and Ollama generation are supported. A real local Ollama `qwen3:8b` call through `POST /answers` answered a synthetic question with the expected page citation. Remote OpenAI and Gemini have transport/configuration coverage only for their applicable paths, with no live cloud verification.
- The reader, comparison/search and assistant citations can save indexed passages. Saved evidence stores a provenance snapshot with editable notes. Markdown export downloads the currently saved notebook. PostgreSQL tests verify idempotent saves, notes and snapshots after synthetic source deletion. Notebook browser edit/export still needs verification.
- New additive migrations use a version ledger and transaction lock. `001_saved_evidence` and `002_document_status_default` applied twice locally without replaying already applied changes. The earlier bootstrap remains in `scripts/init_db.py`.
- Verification at this checkpoint: 50 Python tests pass with `EVIDENCERAG_INTEGRATION=1`. React production build passes. The database fixtures roll back.
- Recovered work pushed as `93b3c82` (providers) and `7e24dea` (reader, notebook,
  migrations and theme). Verified local and remote SHAs matched after that push.
- Comparison Studio selects server-generated indexed excerpts for eight topics from
  workspace-scoped papers. Numeric outcomes carry source-stated metric and
  value, and available evaluation conditions. Per-paper missing results and
  cross-paper protocol differences are explicit. The matrix, claim explorer
  and interactive paper → topic → passage graph link to Reader, Notebook and
  paper-scoped Assistant drafts. Reproducibility checks surface cited mentions
  for manual review. The briefing exports excerpts and author-stated follow-up
  candidates as Markdown. Coverage is limited to ranked passages and exact matching.
- Verification after the numeric excerpt-ID change: 64 PostgreSQL-enabled tests pass,
  including workspace rejection, extraction grounding and method differences.
  React production build passes. Browser-verified the Comparison Studio matrix,
  graph to claim filter, Assistant handoff, reader navigation and Markdown download.
  Real-paper extraction was uneven on the earlier string-ID response format.
  The final numeric-ID contract has automated integrity coverage and a live
  Ollama synthetic smoke test recovered the expected 87% result with its
  exact indexed quote and zero rejected items.
- Recovered structured comparison pushed as `9d95e3d` and confirmed on
  `origin/main`.
- Durable comparison history pushed as `5cda273`. Versioned migration
  `003_comparison_runs` adds run history,
  per-paper progress, partial results, cancellation and a worker lease.
  Applying the migration twice succeeded. PostgreSQL-enabled tests passed
  (67 total), covering progress persistence, failure, stale lease recovery,
  cancellation, and workspace access after a paper leaves the scope.
- Browser verified that a real two-paper run starts with a progress indicator,
  persists to history, completes, and reopens after a full browser reload.
  That run returned 24 rejected selection records and no accepted findings.
  The local-provider diagnostic found valid window selections with omitted
  metric/value keys. The extractor now keeps those as source excerpts and
  copies a numeric value only for one explicit metric/value expression.
  A subsequent live two-paper comparison retained six findings, with 18
  rejected records still surfaced for review. Extraction quality remains
  model-dependent and bounded by sampled passage coverage.
- Evidence Atlas pushed as `dffb2f7`. It reconstructs typed nodes and edges from
  persisted comparison excerpts, rechecks current workspace members and
  turns each edge into a source reference. Browser tested populated desktop
  and 390-pixel views, node-type filtering, keyboard zoom and Reader handoff.
  Full test gate: 72 PostgreSQL-enabled tests, production build and diff check.
- Counterevidence pushed as `5470e35`. It resolves the source finding in scope and retrieves
  other indexed papers with quoted context, qualifying language, and matching
  reported condition labels. Browser tested real results and Reader handoff.
  PostgreSQL tests reject out-of-scope findings and verify self exclusion and
  ranking. Full gate: 74 PostgreSQL-enabled tests and production build.
- Claim assessments pushed as `979bf3f`. Additive migration
  `004_claim_reviews` persists reviewer-assigned support,
  qualification, challenge or uncertainty alongside an independent assessment
  of experiment alignment, a note, and source snapshots. Browser verified form
  controls. PostgreSQL verified save, edit, canonical snapshots and scope
  revocation. Full suite still passes (74).
- Reproducibility Studio pushed as `f23f386`. It checks 11 categories for each scoped paper, separates
  specific wording from general mentions and items not located, and exports
  source-linked Markdown with practical verification steps and draft notes.
  Browser verified real-paper analysis, filter, source link and Markdown
  download. Integration tests verify reported values and workspace rejection.
  Full gate: 76 PostgreSQL-enabled tests and production build.
- Question Coverage pushed as `224b510`. It maps a broad question to local research facets or three
  to five opt-in model-proposed subquestions. Workspace SQL requires both
  topic and facet terms and deduplicates papers. Browser verified actual
  library results, Assistant handoff and state retention. Ollama returned four
  valid subquestions in a live smoke test. Full gate: 79 PostgreSQL-enabled
  tests and production build.
- Research Directions pushed as `22fb392`. It finds five classes of limitation or follow-up language
  in the scoped ranked sample, deduplicates papers and offers editable
  investigation plans. Browser verified real passages, export download, Reader
  handoff and draft retention. PostgreSQL verifies qualifying language,
  deduplication and workspace rejection. Full gate: 81 PostgreSQL-enabled tests
  and production build.
- Evidence Packets pushed as `f1d4037` and confirmed on `origin/main`.
- Additive migration `005_evidence_packets` persists scoped saved-passage
  snapshots, notes, bibliography fields and editable briefings with revision
  checks. Browser verified scoped packet creation, a real local Ollama draft
  using synthetic calibration evidence, saving, HTML export and reopening
  after reload. The disposable packet, passage, document and workspace were
  removed. Full gate: 82 PostgreSQL-enabled tests, 3 frontend export tests
  and production build.
- Imports and metadata pushed as `5dd2e08`, verified on `origin/main`.
  Library import now supports multiple PDFs with per-file queue states and
  retry. Corrupt PDFs are rejected before managed publication. Metadata
  migration `006_document_metadata` adds DOI, venue, tags and revision checks.
  Reader metadata editing and library filter/sort build on these fields.
  Browser verified two actual synthetic imports, metadata editing, DOI
  filtering and PDF page navigation. Byte-identical sources and range requests
  passed. Both hash-identified synthetic records and managed copies were
  removed afterward. Full gate: 84 PostgreSQL-enabled tests, 3 frontend
  export tests and production build.
- Collections pushed as `18eece7` and confirmed on `origin/main`.
  Additive migration `007_collections` supports library and workspace
  collections with case-insensitive unique names and scoped membership.
  Library can create, rename, attach, detach, and filter. Browser tests verified
  state retention, non-destructive removal, and cleanup of the disposable
  empty collection. Full gate: 85 PostgreSQL-enabled tests, 3 frontend
  export tests and production build.
- Reader annotations pushed as `9a84128`. Additive migration
  `008_reader_annotations` stores page bookmarks, exact
  indexed quotes and revisioned notes. Browser verified creating a bookmark,
  highlighting text, saving a note and reopening it via the bookmark. The
  synthetic PDF and annotations were removed afterward. Full gate: 86
  PostgreSQL-enabled tests, 3 frontend tests and production build.
- Integrated PDF Reader pushed as `e086b43`. It renders locally with a lazy-loaded PDF.js worker and selectable
  text. Browser verified phrase search to the correct synthetic source page,
  fit-width and 125% zoom, a no-match result and a 390px layout without
  horizontal page overflow. Source range tests verify the bytes and headers.
  Full gate: 87 PostgreSQL-enabled tests, 5 frontend tests and production build.
- Multi-paper scope pushed as `ab55cfe`. Migration `009_conversation_papers` persists up to 12 explicit
  source IDs per conversation. Both PostgreSQL retrieval paths constrain
  candidates before ranking and the API rechecks workspace scope before
  saving a reply. Browser verified two synthetic workspace papers, a live
  Ollama response that cited both, a citation link to Reader, and reopening
  the saved conversation. Disposable fixtures were removed. Full gate:
  88 PostgreSQL-enabled tests, 5 frontend tests and production build.
- Assistant streaming pushed as `bd7ecd1`. It streams progress through
  NDJSON. A disconnect during generation cancels the exchange before commit.
  Browser verified local Ollama cancellation retained the question without
  messages, then retry saved exactly one cited exchange. Automated tests cover
  ASGI disconnects, transaction rollback and incomplete-stream handling.
  Full gate: 91 PostgreSQL-enabled tests, 7 frontend tests and production build.
- Disagreement checks pushed as `30c8ea8`. Comparison Studio and Evidence Atlas flag explicit opposing comparative
  statements only when both report the same methods and evaluation labels.
  Browser verified a real local Ollama comparison of two synthetic papers, an
  Atlas edge with two source references, a saved assessment and a two-paper
  Assistant handoff. A fallback fills literal labels for explicit source
  clauses. Full gate: 97 PostgreSQL-enabled tests, 8 frontend tests and build.
- Reproducibility disclosures pushed as `7ee9957`. Dossiers evaluate
  24 components across 11 categories.
  Browser verified numeric disclosures, stated data and code limitations,
  original PDF navigation and Markdown export with researcher notes on a
  synthetic paper. Full gate: 98 PostgreSQL-enabled tests, 9 frontend tests
  and production build.
- Focused gap coverage pushed as `895c84d`. Research Directions samples distinct papers within each theme and separates
  author-stated limitations from reported evaluations. Browser verified a
  focused two-paper gap, Markdown export and Assistant handoff with both
  sources selected. Disposable fixtures were removed. Full gate:
  100 PostgreSQL-enabled tests, 9 frontend tests and production build.
- Briefing templates pushed as `f12cf54`. Migration `010_packet_templates` persists seven forms of briefing. The
  editor inserts outlines and citations and catches IDs outside the packet.
  Browser verified a live Ollama abstention for missing methodology, a
  cited question-investigation draft, saving and reopening the template,
  and HTML export. Full gate: 101 PostgreSQL-enabled tests, 10 frontend
  tests and production build.
- Benchmark pushed as `854a8df`. It runs real PostgreSQL retrieval and the answer API
  in a fresh rollback-only schema. Both deterministic and live local Ollama
  modes passed six cases for ranking, workspace isolation, cited values,
  page references and abstention. Live hybrid recall@4 was 1.0 and answer
  p95 was about 3.4 seconds on this small corpus. Full gate:
  104 PostgreSQL-enabled tests, 10 frontend tests and production build.
- Browser regressions pushed as `c09e73f`. They run the real frontend and API against a disposable
  migrated PostgreSQL schema and deterministic model fixtures. Headless
  Chrome passed upload, duplicate and corrupt-file handling, Reader search,
  bookmarks, range download, notebook notes, scoped Assistant citation to page
  2 and linked HTML export. A separate 390px test covered keyboard navigation
  and theme switching. The fixture schema and files were removed.
- Source lifecycle hardening pushed as `cd38fe4`. Publication, byte-identical recovery and deletion share a
  PostgreSQL advisory lock per content hash. Two concurrent connections
  verified that a re-import waits until deletion finishes and retains a
  byte-identical source. A rolled-back import removes only its own
  unreferenced copy. Database error responses omit driver details.
  Full gate: 107 PostgreSQL-enabled tests, 10 frontend tests, two browser
  regressions and production build.
- Embedding rebuilds pushed as `09d6455`. Migration `011_embedding_rebuilds` adds durable rebuild status, cancellation
  and stale-worker detection. Browser tested Reader controls and retention
  of page citations. A real local model rebuilt a synthetic vector while
  keeping passage ID and pages. PostgreSQL tests verified atomic replacement
  and retention after failure, cancellation or interruption. Full gate:
  109 PostgreSQL-enabled tests, 10 frontend tests, two browser tests and build.
- Settings pushed as `6f86e59`. It reports the configured model, local or remote transport,
  PostgreSQL availability and active index coverage. Browser tested the
  diagnostics and provider check with isolated fixtures. Live loopback
  Ollama passed the fixed JSON check in 2.7 seconds without library content.
  Full gate: 111 PostgreSQL-enabled tests, 10 frontend tests, two browser
  tests and production build.
- The local API validates accepted hosts and browser write origins. Answer
  generation receives source fields and prior turns as JSON values and
  rejects IDs from outside the current evidence set. Browser tests verified
  the configured frontend still works. Live Ollama passed all six synthetic
  benchmark cases. Full gate: 114 PostgreSQL-enabled tests, 10 frontend
  tests, two browser tests and production build.
- Claim Explorer pushed as `4c1a6bd`. Migration `012_research_claims` indexes source-backed excerpts from stored
  comparison runs and publishes new claims alongside each paper result. Claim
  Explorer searches by workspace, paper, topic, text and researcher status. It
  displays exact indexed quotations, links to Reader and Atlas, and keeps human
  assessments separate from source selection. Browser-tested comparison to
  assessment to Atlas to Reader. Full gate: 115 PostgreSQL tests, 10 frontend
  tests, three browser tests and the production build.
- Atlas expansion pushed as `f35d06d`. Atlas builds from persisted claims and includes source-matched notebook
  entries, indexed highlights and literal method names. Cross-paper shared
  dataset-and-metric edges cite both passages. The browser test verified graph
  filters, connection to Claim Explorer and both kinds of research artifact.
  Full gate: 116 PostgreSQL tests, 10 frontend tests, three browser tests and build.
- Durable imports pushed as `95523d2`. Migration `013_import_jobs` adds durable PDF staging, queue state and
  recoverable retries. A subprocess exited after the paper committed but before
  the job recorded success. A fresh worker replayed it and retained the same
  document and chunk. Browser verified queue history after reload. Full gate:
  118 PostgreSQL tests, 10 frontend tests, three browser tests and build.
- Page attribution and legacy scope recovery pushed as `cf847a0`. New PDF imports keep chunks inside their physical PDF pages. PostgreSQL
  verified separate citations across a blank page. The Assistant preserves older
  transcripts and requires an explicit paper selection when their original scope
  is unavailable. Known legacy paper scopes and existing index anchors retain
  their saved identifiers. Chrome verified scope selection and a fresh citation
  alongside the archived transcript. Full gate: 122 PostgreSQL tests, 10
  frontend tests, three browser tests and the production build.
- Notebook tags pushed as `a2c86a6`. Migration `014_saved_evidence_tags` adds searchable notebook tags to
  saved passages. Tags and notes are edited independently and retained with
  their source snapshot. Chrome verified reload, filtering across tags and
  notes, and Markdown export. Full gate: 122 PostgreSQL tests, 10 frontend
  tests, three browser tests and the production build.
- The public reading-comprehension benchmark pushed as `bf11dcf` adds five answer cases and eight
  research workflow checks from three published papers. It exercises
  statement-level citation support, metric association, comparability,
  contradiction false positives, source-backed directions and reproducibility.
  The comparison validator rejects a number explicitly associated with a
  different metric. Explicit model abstention discards stray generated claims.
  All five cases passed in the final local Ollama and live-embedding run.
  Hybrid recall@4 was 1.0, strict keyword recall@4 was 0.25, and answer p95 was
  3.7 seconds. The corpus covers a single domain with annotated excerpts.
  Full gate: 126 PostgreSQL tests, 10 frontend tests and the production build.
- Flagship screen refinement pushed as `56ef0d7`. Inspected Library, Reader, Comparison Studio, Claim Explorer, Evidence Atlas
  and Assistant in Chrome at 1280 px and 390 px, with desktop screenshots in
  both themes. The mobile menu stays available after loading PDF.js.
  The comparison table scrolls inside its panel, and Atlas centers the selected
  evidence with its related sources. Library prioritizes papers above import
  history, Reader prioritizes the PDF, and Assistant distinguishes questions
  from cited replies. Full gate: 126 PostgreSQL tests, 10 frontend tests,
  three browser tests with layout assertions across all six screens, and the
  production build.
- Reading progress pushed as `9545eff`. Migration `015_document_reading` adds per-paper reading status and page
  resume. Library filters and sorts by progress, and explicit citations
  still open on their recorded page. PostgreSQL verified invalid pages,
  finished-state retention and legacy source ranges. Chrome verified resume
  after reload and a citation that opened a different page. Full gate:
  127 PostgreSQL tests, 10 frontend tests, three browser tests and build.
- Staging recovery pushed as `4d9d14f`. Migration `016_import_stage_cleanup` lets the worker remove known staged
  files from terminal jobs after restart. A subprocess crashed after
  completion committed, and the next worker cleared the staged copy.
  The source PDF, indexed passage, retryable upload and unrelated file
  retained their original contents. Full gate: 128 PostgreSQL tests, 10
  frontend tests, three browser tests and the production build.
- The notebook milestone `42d2b85` can now filter saved passages and Reader highlights by
  workspace and paper collection. PostgreSQL tests verified detached papers
  are inaccessible in their former scope and stale anchors retain the
  original excerpt. Chrome verified filtered annotation search and opening
  the same source twice. Full gate: 129 PostgreSQL tests, 10 frontend
  tests, three browser tests and build.
- Reader recommendations pushed as `0b6c2bb`. Reader shows related papers with matching reported dataset and metric labels
  in the current comparison scope. Both claims remain inspectable from the
  result. PostgreSQL verified source pages, workspace isolation and exclusion
  after detachment. Chrome verified the related paper and both claim links.
- Whole-report evaluation pushed as `735a2fe`. The pinned NREL benchmark imported 52 pages and 104 passages in
  isolation and downloaded byte-identical source bytes. Retrieval found the
  required pages and values in all three numeric cases. New imports index
  captioned, ruled table rows individually with column names and page anchors.
  Live Ollama answers remain a separate quality gap. Runs selected values
  from the wrong row, confused sections, and sometimes returned invalid
  response schemas. Existing indexed passages were preserved.
- Hybrid search now falls back to partial natural-language keyword matches
  when exact lexical search returns nothing. PostgreSQL tests checked workspace
  isolation and explicit search syntax. On the small reading-comprehension
  corpus, keyword recall@4 increased from 0.25 to 1.00 and hybrid recall@4
  stayed at 1.00 in the fixture run. Full gate: 132 PostgreSQL tests, 10
  frontend tests, three Chrome workflows and build.

## Outstanding

1. Improve live answer validation and table-row qualifier matching on the NREL
   whole-PDF suite. Re-run citation support across more independent papers and
   models.
2. Test larger corpora and review legacy passages with several pages.

## Continuation

- Product decisions are in [PRODUCT_STRATEGY.md](PRODUCT_STRATEGY.md). The journey
  and verification matrix is in [ROADMAP.md](ROADMAP.md).
- Run `EVIDENCERAG_INTEGRATION=1 .venv/bin/pytest -q` against the local database
  and `npm --prefix frontend run build` with Node on `PATH`. Test migrations
  with `.venv/bin/python -m app.db.migrations`. Confirm push by comparing
  `git rev-parse HEAD` with `git ls-remote --heads origin main`.
- Keep private PDFs, environment files and generated artifacts out of Git.
  Preserve existing PostgreSQL records and use rollback-only fixtures or
  explicitly disposable test artifacts. Live cloud verification requires credentials.
