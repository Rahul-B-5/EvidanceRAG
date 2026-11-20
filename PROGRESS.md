# EvidenceRAG progress

## Verified

- Repository uses `main` and pushes to `Rahul-B-5/EvidanceRAG`. See `git log` and `git ls-remote --heads origin main` for current delivery status.
- Local PostgreSQL with pgvector uses configured port 5433. Existing library has two papers and 34 indexed passages. Earlier smoke tests verified PDF import, duplicate detection, search, download and disposal of synthetic test records. Existing legacy papers still need byte-identical reimport to restore the original PDF links.
- React has dedicated light and dark themes, a searchable keyboard command palette, a sortable library and a reader with page controls, adjustable split and indexed page passages. Browser verification covered theme switching, Ctrl/⌘K with keyboard selection, opening a real library record, advancing a page and resizing with the keyboard. Browser rendering of an imported original PDF remains outstanding.
- Search, comparison passages and answers support workspace scope. Workspace membership is query scoping within a single-user app. Browser verification previously covered search and two-paper passage comparison. Membership mutations and chat reload still need browser verification.
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
  `origin/main`. Versioned migration `003_comparison_runs` adds run history,
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
- Durable comparison history pushed as `5cda273` and confirmed on
  `origin/main`. Evidence Atlas reconstructs typed nodes and edges from
  persisted comparison excerpts, rechecks current workspace members and
  turns each edge into a source reference. Browser tested populated desktop
  and 390-pixel views, node-type filtering, keyboard zoom and Reader handoff.
  Full test gate: 72 PostgreSQL-enabled tests, production build and diff check.
- Atlas committed as `dffb2f7` and confirmed on `origin/main`.
  Counterevidence search resolves the source finding in scope and retrieves
  other indexed papers with quoted context, qualifying language, and matching
  reported condition labels. Browser tested real results and Reader handoff.
  PostgreSQL tests reject out-of-scope findings and verify self exclusion and
  ranking. Full gate: 74 PostgreSQL-enabled tests and production build.
- Counterevidence committed as `5470e35` and verified on `origin/main`.
  Additive migration `004_claim_reviews` persists reviewer-assigned support,
  qualification, challenge or uncertainty alongside an independent assessment
  of experiment alignment, a note, and source snapshots. Browser verified form
  controls. PostgreSQL verified save, edit, canonical snapshots and scope
  revocation. Full suite still passes (74).
- Claim assessments pushed as `979bf3f` and confirmed on `origin/main`.
  Reproducibility Studio checks 11 categories for each scoped paper, separates
  specific wording from general mentions and items not located, and exports
  source-linked Markdown with practical verification steps and draft notes.
  Browser verified real-paper analysis, filter, source link and Markdown
  download. Integration tests verify reported values and workspace rejection.
  Full gate: 76 PostgreSQL-enabled tests and production build.
- Reproducibility Studio pushed as `f23f386` and confirmed on `origin/main`.
  Question coverage maps a broad question to local research facets or three
  to five opt-in model-proposed subquestions. Workspace SQL requires both
  topic and facet terms and deduplicates papers. Browser verified actual
  library results, Assistant handoff and state retention. Ollama returned four
  valid subquestions in a live smoke test. Full gate: 79 PostgreSQL-enabled
  tests and production build.
- Question coverage pushed as `224b510` and confirmed on `origin/main`.
  Research Directions finds five classes of limitation or follow-up language
  in the scoped ranked sample, deduplicates papers and offers editable
  investigation plans. Browser verified real passages, export download, Reader
  handoff and draft retention. PostgreSQL verifies qualifying language,
  deduplication and workspace rejection. Full gate: 81 PostgreSQL-enabled tests
  and production build.
- Evidence Packets pushed as `f1d4037` and confirmed on `origin/main`.
  Library import now supports multiple PDFs with per-file queue states and
  retry. Corrupt PDFs are rejected before managed publication. Metadata
  migration `006_document_metadata` adds DOI, venue, tags and revision checks.
  Reader metadata editing and library filter/sort build on these fields.
  Browser verified two actual synthetic imports, metadata editing, DOI
  filtering and PDF page navigation. Byte-identical sources and range requests
  passed. Both hash-identified synthetic records and managed copies were
  removed afterward. Full gate: 84 PostgreSQL-enabled tests, 3 frontend
  export tests and production build.
- Imports and metadata pushed as `5dd2e08`, verified on `origin/main`.
  Additive migration `007_collections` supports library and workspace
  collections with case-insensitive unique names and scoped membership.
  Library can create, rename, attach, detach, and filter. Browser tests verified
  state retention, non-destructive removal, and cleanup of the disposable
  empty collection. Full gate: 85 PostgreSQL-enabled tests, 3 frontend
  export tests and production build.
- Collections pushed as `18eece7` and confirmed on `origin/main`.
  Additive migration `005_evidence_packets` persists scoped saved-passage
  snapshots, notes, bibliography fields and editable briefings with revision
  checks. Browser verified scoped packet creation, a real local Ollama draft
  using synthetic calibration evidence, saving, HTML export and reopening
  after reload. The disposable packet, passage, document and workspace were
  removed. Full gate: 82 PostgreSQL-enabled tests, 3 frontend export tests
  and production build.
- Additive migration `008_reader_annotations` stores page bookmarks, exact
  indexed quotes and revisioned notes. Browser verified creating a bookmark,
  highlighting text, saving a note and reopening it via the bookmark. The
  synthetic PDF and annotations were removed afterward. Full gate: 86
  PostgreSQL-enabled tests, 3 frontend tests and production build.

## Outstanding

1. Add integrated PDF text search, zoom and richer page rendering. Refine
   page attribution for chunks that span several pages.
2. Add contradiction candidates only for aligned study conditions and opposing
   claims with two citable sources. Add reproducibility disclosure validation,
   corpus-scoped gap exploration and evidence-grounded research briefings.
3. Expand graph exploration across workspaces and notebook sources.
4. Extend the notebook with tags, collections, annotations and bibliography export. Add browser coverage for save, edit, reopen and export. Add source view smoke coverage using a synthetic PDF.
5. Add retrieval and answer evaluation fixtures, quality/latency reporting and automated browser regressions. Identifier validation does not establish factual entailment.
6. Harden ingestion lifecycle, source cleanup races, legacy conversation scope backfill and re-embedding. Upgrade the local Node runtime from Node 20 to a supported release when convenient.

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
