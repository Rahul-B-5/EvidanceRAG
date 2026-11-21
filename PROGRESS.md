# EvidenceRAG progress

## Current release audit

The entries below describe the current checkout. The implementation history
that follows records earlier checkpoints and their remaining work at the time.

| Requirement | Current evidence | Remaining release work |
| --- | --- | --- |
| Existing research data | PostgreSQL 5433 retains 3 documents and 75 passages. Recovered the legacy original through byte-identical duplicate upload and verified unchanged document metadata and a digest of every chunk row, including embeddings. | Continue read-only integrity checks at release gates. |
| Local launch | Supported launcher checks ports, PostgreSQL and additive migrations. Latest checkout loaded the existing 3-paper, 75-passage library in Chrome through both loopback hostnames. Shutdown released both service ports. | Repeat smoke testing when startup dependencies change. |
| AI configuration | Encrypted web profiles cover five providers, answering/extraction routing, local discovery and live model switching. Native Ollama context configuration is browser-tested. | Authenticated cloud calls need configured credentials. |
| Library and Reader | Durable imports, duplicate handling, restart recovery, indexed pages, bookmarks, annotations and exact passage navigation have integration and browser coverage. | Scanned PDFs require OCR outside the current text ingestion path. |
| Research workflows | Browser journeys cover comparison, claims, Atlas, opposing findings, reproducibility, directions, coverage, evidence packets and exports. | Wider representative scientific evaluation and assistive-technology testing. |
| Scientific grounding | Qwen and Gemma each passed all four full NREL report cases. Qwen passed all five published-paper excerpt cases with live embeddings and generation. Gemma initially included extra split values, then passed all five after the scope instruction change. | Repeat across additional papers and formats. Exact source matching does not independently verify all scientific interpretations. |
| Recovery and cancellation | Browser verifies acknowledged cancellation, no partial exchange after reload and successful retry. Provider-failure recovery has a separate browser regression. | Multiple backend workers need shared cancellation state or affinity. |
| Performance | Synthetic retrieval measured up to 500 papers and 30,000 passages. A 24-PDF burst used real embeddings. | Concurrent, larger and more varied full-PDF workloads. |

## Implementation history

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
- Answer format and grouped citations pushed as `b32d24d`. Assistant requests the answer schema from Ollama and Gemini and validates
  every returned citation ID, including IDs in grouped citations. The latest
  live Gemma run passed two of four NREL cases. It returned valid answer
  objects for all four, selected the wrong utility-scale row in the
  section comparison, and returned an explanation instead of abstaining
  for the missing installer quote. Full gate: 134 PostgreSQL tests, 10
  frontend tests, three Chrome workflows and build.
- PDF section citations pushed as `1f185a3`. Migration `017_chunk_outline` adds optional section metadata to new chunks.
  Reader and Assistant use the original PDF's top-level outline and keep the
  physical page link. Chrome confirmed the citation label and link target.
  The second Gemma run still passed two of four whole-report cases. It cited the
  correct summary section but chose the storage row from Table 3 and failed the
  explicit abstention check. Full gate: 135 PostgreSQL tests, 10 frontend tests,
  three Chrome workflows and build.
- Source links from Assistant, Claim Explorer, Comparison Studio, Atlas,
  related papers and saved evidence identify the exact indexed passage.
  PostgreSQL verified that passage 26 can be prioritized within a 25-passage
  page view and that it cannot be selected on a different page. Chrome
  verified the cited passage appears on its PDF page. Full gate: 136
  PostgreSQL tests, 10 frontend tests, three Chrome workflows and build.
- Tested an extra model-based table verification pass on the full report.
  It withheld a supported community-solar answer and let the unsupported
  utility-scale answer through, so the experiment was removed. The public
  PDF benchmark now records abstention reasons alongside the answers and
  citations to help diagnose this failure.

## Outstanding

The final-completion brief adds web-based provider setup, a supported local
launcher, wider browser review and release validation to the previous scope.

1. Expand numerical grounding beyond explicit exclusions in named tables.
   Tighten the association between the requested metric and cited prose values,
   and verify stability across repeated runs and additional scientific PDFs.
2. Test larger imported corpora, concurrent load, and legacy passages with
   several pages. Local retrieval timing is available for up to 30,000
   synthetic passages in the latest benchmark run.
3. Verify authenticated cloud providers against real accounts when credentials
   are available. Expand end-to-end testing for extraction profile selection.

## Local launch verification

- Launcher pushed as `5c6b70a`. Vite previously listened on IPv6 loopback only. The npm development command
  now binds to IPv4 loopback explicitly. The launcher checks dependencies,
  ports, PostgreSQL and migrations before reporting readiness. Chrome loaded
  the application and its library through both `localhost` and `127.0.0.1`.
  A second launcher reported the occupied API port. Terminating the launcher
  released both listeners. The live library already contained three papers
  and 75 passages at startup. The launcher used the existing database and the
  browser smoke test only read those records.
- Launcher gate passed 136 PostgreSQL tests, 10 frontend tests, three Chrome
  workflows and the production build.

## AI provider configuration

- Migration `018_generation_profiles` adds encrypted provider profiles for
  answering and extraction. Settings discovers local Ollama models, accepts
  custom connection information and tests with synthetic prompts. The
  answering profile also applies to packet drafts. Comparison and coverage
  use the extraction profile and fall back to the answering profile when unset.
- PostgreSQL tests verified ciphertext storage, local access limits, revisions
  and live task selection. Chrome used two different Assistant models without
  restarting and verified the selection after reload. Desktop, dark and
  narrow Settings screenshots were inspected. Local Ollama passed live
  synthetic probes for Gemma and Qwen. Native Claude was tested with mocked
  requests and error responses. Authenticated cloud calls remain unverified.
- Provider gate passed 138 PostgreSQL tests, 10 frontend tests, four Chrome
  workflows and the production build.

## Typed table evidence

- Additive migration `019_table_row_evidence` stores captions, row
  groups and column-to-cell mappings for new passages. Reader shows their
  cells alongside the original PDF, and Assistant receives the typed evidence.
- The live Gemma run passed three of four NREL cases, including abstention on
  a missing installer quote. For the cross-section case, retrieval surfaced
  the correct utility-scale row and Executive Summary passage. Generation
  still selected the storage-inclusive value from the neighboring table row.
  The next milestone is to enforce metric-and-condition matches before
  accepting a numerical table claim.
- Passed 139 PostgreSQL tests, 10 frontend tests, five Chrome workflows
  and the production build.

## Condition-aware table grounding

- Assistant can scope an explicit named-table question to a single matching
  row and the requested metric columns. The check accepts a condition stated
  in the row, or a baseline and a companion row explicitly adding that
  condition. The latter can use an unambiguous abbreviation defined by the
  source document. Ambiguous selections or altered table units trigger
  abstention. Named prose sections retain separate citations.
- The public NREL gate now checks the exact Table 3 row, column and unit.
  One full Gemma run passed all four cases and preserved separate citations
  for the $1.16/Wdc Executive Summary value and $1.17/Wdc Table 3 value.
  Another run abstained on the cross-section answer. The cross-section
  response still needs repeatability checks, and the named prose evidence
  check verifies the cited numbers without independently interpreting every
  qualification. The benchmark reimported the report only in a temporary
  schema and verified the source download byte for byte.
- Passed 148 PostgreSQL tests. The new regressions cover distractor columns,
  wrong units, raw table text citations, ambiguous matches and ambiguous
  abbreviations.

## Local scale check

- Ran 20 warm samples per operation on the local PostgreSQL 17.11 server.
  At 250 papers and 15,000 passages, the whole-library hybrid p95 was 51.6 ms.
  At 500 papers and 30,000 passages, it was 104.2 ms. At 500 papers, the
  library listing p95 was 13.5 ms, keyword 52.7 ms, and vector 34.2 ms.
  A ten-paper workspace returned the correct scope at a p95 of 12.7 ms.
- These measurements use synthetic 384-dimensional vectors and repeated
  research text. They include connection setup. Model latency, PDF parsing,
  frontend rendering and concurrent load still need separate measurements.
- A separate burst of 24 four-page synthetic PDFs completed through the
  import-jobs API and real local embeddings in 2.3 seconds. All 96
  page-anchored passages were indexed and a source download matched the
  original bytes. This run used one worker and short text pages.

## Research screen review

- Added desktop light, desktop dark and narrow screenshots for Overview,
  Reproducibility, Research directions and Evidence packets. The view review
  led to a compact mobile header, full-width narrow research selectors and
  top-aligned research results and editors.
- Reproducibility, Research directions, Question coverage and Evidence
  packets now link readers to the exact indexed passage, retaining the
  workspace when the result is scoped. Browser fixtures verify passage
  targets in the dossier, directions and packet, as well as real Markdown
  and HTML downloads.
- In the optional live browser test, Settings discovered and saved both
  Gemma and Qwen against the local Ollama server. Both answered from an
  isolated synthetic PDF in the same running application and linked to
  the exact passage on page 2. Confirmed by read-only counts that the
  existing database on port 5433 still has 3 papers, 75 passages and 19
  applied migrations.
- Release gate passed 148 PostgreSQL tests, 10 frontend tests, six Chrome
  workflows including live Ollama, and the production build.

## Visible measurement provenance

- Assistant citations now show the table columns and exact cell values
  accepted by the named-table check. Chrome verified the values survived
  conversation reload and that the citation focused the exact row on the
  original PDF page. Desktop and narrow screenshots were inspected.
- Both deterministic corpora passed all 11 answer cases and eight
  scientific checks across comparability, contradiction, coverage and
  reproducibility. The separate live Qwen 8B run on the full NREL PDF
  passed the installer-quote abstention. It omitted citations in two
  numerical answers and abstained on the cross-section comparison.
- Passed 149 PostgreSQL tests, 10 frontend tests, six Chrome workflows
  including live Ollama, an exact-source browser rerun and the build.
- Measurement validation preserves case in units. The regression rejects
  milliwatts when the source cell reports megawatts. A subsequent full
  Gemma run passed all four NREL cases with case-sensitive unit validation.
- A separate restart smoke test ran two backend process IDs against a
  disposable schema and upload directory. The completed import,
  byte-identical PDF, bookmark and cited conversation survived restart.
- Named rows with an explicit exclusion must match the question's full
  subject label. A variant sharing the reference model's name cannot
  supply its metric. Questions asking for both conditions bypass the
  exclusion-only check. Passed 151 PostgreSQL tests and the exact-row
  Chrome workflow.
- Next release gate is repeatable cross-section grounding across models.
  Replace general numeric occurrence checks on cited prose with a
  measurement tied to the requested metric, condition and original unit.
  Preserve a separate citation for each source. Authenticated cloud
  providers and concurrent whole-library import still need live checks.
  The live settings database and server fallback currently have no
  configured cloud credentials.
- Tried a general array of claims with structured evidence IDs. The
  PostgreSQL and synthetic browser checks passed. Qwen timed out on both
  ordinary numeric report cases, abstained on the comparison, and returned
  unrelated background on the missing-quote case. The experimental
  contract was removed. A native Ollama token probe then measured 6,132
  and 6,562 prompt tokens for the residential and community cases at an
  8,192-token context. The 4,096-token context reported only 2,050 tokens
  for each of those prompts. The scoped comparison fit at 1,927 tokens
  in both contexts. Test retrieval packing or an explicit context setting
  before redesigning the response shape again.

## Local Ollama context setting

- Added optional per-profile context sizes under Settings → AI Providers →
  Advanced connection. A selected size uses the native loopback Ollama
  transport, and a blank field uses the existing server default. Migration
  `020_ollama_context_tokens` adds a nullable column and leaves existing
  profiles in place.
- Chrome rejected an invalid size, persisted 8,192 tokens, and exercised
  the native transport against both installed Gemma and Qwen models.
  The full gate passed 152 PostgreSQL tests, 10 frontend tests, six Chrome
  workflows and the production build. The live database still contains
  3 papers and 75 passages on port 5433 after the additive migration.
- The native probe and the implemented provider both passed three of four
  live NREL cases with Qwen at 8,192 tokens. The two numeric cases now
  return cited answers, and the missing quote still produces abstention.
  The cross-section case still abstains, including when the prompt fits.
  Its remaining accuracy work is to bind the prose measurement to the
  requested metric and condition and preserve the two source citations.

## Continuation

- Final live verification exposed intermittent comparison rejection and an
  incorrect abstention flag from Gemma. Added a conservative extractive
  fallback for scoped table comparisons. It presents verified table cells
  and one unambiguous source measurement per requested section, with separate
  citations and an explicit “Extracted source measurements” heading.
  Ambiguous sections still abstain.
- Explicit statements that the supplied evidence lacks the requested fact
  now normalize to abstention. Regression coverage distinguishes that case
  from a scientific finding of no statistically significant effect.
  Passed 169 PostgreSQL tests and all four live NREL report cases with Gemma.
  The tracked-file audit found no private PDFs, environment file, provider
  key or matching credential patterns.
  After resume, the interrupted browser failures did not reproduce in a
  fresh full run. Seven deterministic Chrome workflows passed. Added a
  deliberately incorrect neighboring-value provider fixture and verified
  that extractive recovery shows the correct cell, persists after reload
  and opens its exact Reader row. Multi-column recovery and ambiguous
  section regressions passed in the full 170-test PostgreSQL gate.

- Comparison scale checks now retain SI prefix case. They flag MW versus
  mW, MB versus Mb, kJ versus J and ms versus s as different reported scales.
  Word aliases such as percent/% and seconds/s still match. An extraction
  regression checks the original reported power units survive into the
  pairwise comparison. Passed 165 PostgreSQL tests, the Comparison Studio
  browser workflow and all five scientific excerpt evaluation cases.
  The supported launcher also passed a read-only live library smoke test
  in Chrome through localhost and 127.0.0.1, then released both ports on
  shutdown. The frontend production build passed.

- Added provider-failure browser recovery. It checks the retained question,
  an empty persisted conversation after reload, a cited retry and removal of
  the error state. Seven deterministic Chrome workflows passed.
- Ran live embeddings and generation on the published-paper excerpt suite.
  Qwen passed five of five. Gemma first passed four, adding development
  metrics to a test-only question. The answer instruction now requests only
  the specified split and conditions. Gemma then passed five of five.
  This improves adherence but still requires evaluation on broader material.
- Recovered the existing legacy PDF from a byte-identical local copy
  through POST /documents. All three source endpoints now return bytes
  matching their recorded hashes. Existing metadata and all indexed chunk
  rows were verified unchanged. Passed 158 PostgreSQL tests, 10 frontend
  tests and the build.

- A new browser cancellation regression exposed a race where closing the
  stream could precede server disconnect detection and permit a late result
  to save. Assistant now sends its UUID request token to an explicit cancel
  endpoint before closing the stream. The worker checks cancellation before
  saving, and the stream reports cancellation to clients that keep listening.
- Chrome held an actual provider call, cancelled it, released it afterward,
  reloaded the empty conversation and retried successfully. A backend
  regression verifies the worker cannot reach saving and the request token
  is removed when it finishes. Passed 158 PostgreSQL tests, 10 frontend
  tests, six deterministic Chrome workflows and the production build.
- Cancellation tokens are held by the active backend process. Deployment
  across multiple worker processes needs shared cancellation state or request
  affinity. The supported local launcher runs one backend process. Cloud
  authentication and broader scientific evaluation remain pending.

- Browser verification now covers local Question Coverage, exact source
  navigation and subquestion planning through the saved extraction profile.
  The fixture rejects planning requests sent to the answering model.
  Reviewed desktop, dark and narrow screenshots and fixed the mobile
  question form so its input spans the available width. Both affected
  browser workflows, all 10 frontend tests and the build passed.

- Opposing findings now use Reader links with the exact indexed passage
  and workspace. Browser PDF fixtures include opposite reported outcomes
  under the same dataset, task, split and protocol. Chrome verified both
  statements and opened the original quoted passage on page 2. Inspected
  the rendered two-source panel and captured light, dark and narrow
  comparison layouts. Passed 157 PostgreSQL tests, 10 frontend tests,
  five deterministic Chrome workflows and the production build.

- Expanded the scoped prose measurement check to common scientific units.
  A latency claim cannot replace milliseconds with seconds or omit the
  source unit. A later measurement for a different metric in the same
  sentence is excluded from support. Passed 157 PostgreSQL tests, the
  Reader citation browser workflow and all five published-paper excerpt
  cases. The full Qwen report rerun at 8,192 tokens passed all four cases.

- Provider verification now covers the complete comparison-to-briefing
  browser journey. The fixture server resolves saved extraction profiles
  through the real provider factory. Its endpoint rejects structured
  extraction sent to the answering model. Chrome configured different
  answering and extraction models, ran a comparison, saved its evidence
  and generated a briefing using the answering model without restarting.
  All five deterministic browser workflows and the frontend build passed.
  The optional live Ollama workflow remains separately available.

- Gemma's comparison joined two measurements in one sentence with separate
  citations. The grounding check now separates a cited numeric clause joined
  by “and”, “while” or “whereas” before checking each source. Regression
  coverage rejects swapped sources. The full Gemma run at 8,192 tokens
  passed all four report cases. Qwen's full four-case pass is recorded above.
  Passed 156 PostgreSQL tests and six Chrome workflows including both
  installed models on the current row-identifier path.
- Continue with broader table formats, metric/condition interpretation and
  the requirement-by-requirement release audit. These two model runs cover
  one report and do not establish general scientific correctness.

- Resolved the latest Qwen cross-section abstention. It returned both
  correct measurements but included the source's capacity and numbered
  section title in the table statement. Validation now permits exact
  qualified identifiers from the row label and exact section titles.
  Changed capacities and capacity units remain rejected.
- The full Qwen 8B report run at 8,192 tokens passed all four cases with
  separate PDF page 7 and 45 citations. Passed 156 PostgreSQL tests and
  the exact-source Chrome workflow. The prior full browser and frontend
  build gates remain recorded above. Repeat across models and expand
  source-grounding evaluation before the final release audit.

- Latest prose grounding milestone selects statements matching the requested
  row and metric, excludes explicitly different conditions and checks currency
  and percentage units against the focused excerpt. Regressions reject a
  competing metric in the same sentence and a substituted model variant.
  Passed 155 PostgreSQL tests, 10 frontend tests, five deterministic Chrome
  workflows, the build, and all five reading-comprehension cases with eight
  research checks.
- Ollama was stopped at continuation. Started the installed service on
  loopback and reran the full Qwen 8B report gate at 8,192 tokens. Three of
  four cases passed. The section comparison still abstains. Next inspect
  the candidate response before validation and determine whether it omits
  a required source or adds contextual numbers to the table statement.
  Keep the exact row, unit and two-source requirements.

- Product decisions are in [PRODUCT_STRATEGY.md](PRODUCT_STRATEGY.md). The journey
  and verification matrix is in [ROADMAP.md](ROADMAP.md).
- Run `EVIDENCERAG_INTEGRATION=1 .venv/bin/pytest -q` against the local database
  and `npm --prefix frontend run build` with Node on `PATH`. Test migrations
  with `.venv/bin/python -m app.db.migrations`. Confirm push by comparing
  `git rev-parse HEAD` with `git ls-remote --heads origin main`.
- Keep private PDFs, environment files and generated artifacts out of Git.
  Preserve existing PostgreSQL records and use rollback-only fixtures or
  explicitly disposable test artifacts. Live cloud verification requires credentials.
