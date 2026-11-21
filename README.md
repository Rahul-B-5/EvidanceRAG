# EvidenceRAG

EvidenceRAG is a local-first, evidence-grounded research library for PDF
papers. It extracts papers, stores content-addressed source copies, indexes
hybrid keyword/vector evidence, and returns source-linked answers.

## Run locally

### Existing installation

From the project directory, run the launcher with your existing `.env`.

```bash
.venv/bin/python -m scripts.run_local
```

The launcher checks ports 8000 and 5173, connects to PostgreSQL, applies
pending migrations, and waits for both services to respond. Open
[EvidenceRAG](http://127.0.0.1:5173) and press Ctrl+C in the launcher terminal
to stop both services.

### Clean installation

Install Python 3.11+, Node 22.13+, and PostgreSQL with pgvector available.
Create an empty database and configure its connection in `.env` from
`.env.example`. The example uses PostgreSQL port 5433. Then run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
.venv/bin/python scripts/init_db.py
.venv/bin/python -m scripts.run_local
```

For separate development terminals, use `.venv/bin/uvicorn app.api.main:app
--host 127.0.0.1 --reload --no-access-log` and `npm --prefix frontend run dev`.

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.
The API defaults to loopback hostnames. Set `API_ALLOWED_HOSTS` for an
explicitly configured proxy hostname and `CORS_ORIGINS` for the browser
frontend. Browser mutations require a same-origin request or a configured
frontend origin. Local CLI requests do not need an Origin header.
The application is served at `http://127.0.0.1:5173` and uses the local API at
`http://127.0.0.1:8000` by default. Set `VITE_API_URL` to change that address.

## Core endpoints

- `GET /health` — checks database reachability.
- `GET /settings` — reports the active generation configuration, PostgreSQL
  reachability, and embedding coverage without exposing credentials.
- `GET /claims` searches persisted comparison claims by text, workspace,
  paper, topic and assessment status. `GET /claims/{id}` includes related
  claims with their shared study labels. Use `PUT /claims/{id}/assessment`
  for revision-checked human assessments. Claim Explorer links to Reader,
  Evidence Atlas and the original excerpts.
- `GET /evidence-atlas` combines persisted claims and exact indexed anchors
  for notebook passages and Reader annotations. Shared dataset and metric
  links point to both source excerpts.
- `POST /settings/test-provider` — accepts `{"synthetic": true}` and checks
  JSON generation with a fixed prompt containing no library excerpts.
- `GET /documents` — lists library metadata and chunk counts.
- `GET /documents/{document_id}` — returns document metadata and processing status.
- `PATCH /documents/{document_id}/metadata` — updates title, authors, publication
  year, venue, DOI and tags using a metadata revision. Source and passage IDs persist.
- `GET/POST /collections`, `GET/PATCH /collections/{id}`, and
  `PUT/DELETE /collections/{id}/documents/{document_id}` — manage collections
  and paper membership within a library scope.
- `POST /documents` — imports one PDF as multipart field `file`.
- `POST /import-jobs` queues the same multipart PDF for durable background
  indexing. `GET /import-jobs` shows the queue and recent outcomes.
  `POST /import-jobs/{id}/retry` retries recoverable failures from retained
  bytes. Library uses the durable queue. Queued or interrupted work resumes
  on startup, and replay uses the existing content-hash duplicate check.
  A restarted worker also removes known staged copies from completed jobs.
  Retryable uploads keep their staged input.
- `GET /documents/{document_id}/source` — serves a persisted original PDF.
- `GET /documents/{document_id}/passages?page=...` — lists indexed chunks intersecting the page.
  `focus_chunk` brings the cited passage to the top of that page's result, even
  when the page has more passages than the regular list can show.
- `GET /documents/{document_id}/related-papers` lists papers with source-backed
  result claims that report the same dataset and metric. Reader links to the
  related page and both claims. The optional `workspace_id` restricts matches
  to that workspace's comparison claims.
- `GET /documents/{document_id}/embeddings` — reports the active profile,
  compatible passage count, and most recent rebuild state.
- `POST /documents/{document_id}/embeddings/rebuild` — queues an atomic rebuild
  from existing indexed text. Cancel through
  `POST /documents/{document_id}/embeddings/rebuild/{job_id}/cancel`.
- `GET /documents/{document_id}/reader-annotations?page=...` — lists bookmarks
  for the paper and highlights for the open page.
- `PUT/DELETE /documents/{document_id}/reader-bookmarks/{page}` — saves or removes
  a page bookmark.
- `POST /documents/{document_id}/reader-highlights` and
  `PATCH/DELETE /documents/{document_id}/reader-highlights/{highlight_id}` —
  save indexed text by Unicode character offsets and manage revisioned notes.
- `GET /documents/{document_id}/reproducibility` — scans ranked passages for
  24 reproducibility components in 11 categories, with source excerpts for
  reported details and access limitations. An optional `workspace_id` limits
  the scope.
- `POST /research/coverage` — builds a workspace-scoped question map. It
  requires both question terms and facet terms in each passage and shows at
  most one result per paper per facet.
- `GET /research/directions` — finds indexed limitations and separate
  reported evaluations across a workspace, with a draft experiment plan and
  page references. An optional `focus` matches a method or dataset within
  the supporting statement. The scan samples up to three passages per
  paper and up to 96 per theme.
- `GET/POST /evidence-packets`, `GET/PATCH /evidence-packets/{id}`, and
  `POST /evidence-packets/{id}/draft` — assemble, reopen, edit and draft
  research briefings using immutable saved-passage snapshots.
- `GET /evidence-packets/templates` — lists seven briefing outlines. The
  chosen `template` persists with the packet and guides provider drafts.
- `DELETE /documents/{document_id}` — removes the document, its chunks, and its
  managed source file after the database transaction commits.
  Import and deletion of the same PDF are serialized by its content hash.
  A failed import cleans up a newly published file only after PostgreSQL
  confirms it has no reference.
- `GET /search?query=...` — returns hybrid-retrieved evidence passages.
- `POST /answers` — creates an answer with evidence citations using the configured provider.
- `POST /answers/stream` — accepts the same request and returns NDJSON phase
  updates followed by one validated answer or error. The Assistant uses this
  endpoint for progress and cancellation. Cancelling before commit keeps
  the question available for retry. The browser sends an explicit cancellation
  request and waits for acknowledgement before closing its stream.
  Clients can supply a UUID `request_id` and cancel it through
  `POST /answers/stream/{request_id}/cancel`.
  A provider call already in progress can
  continue until the provider responds or times out.
- `GET /saved-evidence` and `PUT/PATCH /saved-evidence/{chunk_id}` — list and save
  provenance snapshots, and edit passage notes. Saved evidence exports to Markdown.
- `GET /saved-evidence/highlights` searches Reader highlights and their notes.
  Saved passages and highlights both accept `workspace_id` and `collection_id`.
  The notebook keeps scope on source links and flags highlights whose indexed
  text has changed.
- `PUT /saved-evidence/{chunk_id}/tags` replaces the passage's tags. The notebook
  filters by tag and searches titles, passages and notes. Markdown exports include
  saved tags and notes.
- `POST /conversations` and `GET /conversations/{conversation_id}` — persist
  research-assistant conversation history and cited assistant responses.
- `POST /conversations/{conversation_id}/restore-scope` assigns an explicit
  paper selection to a legacy conversation whose scope could not be recovered.
  The existing transcript stays visible, and new answers require a saved scope.
- `GET /conversations` — lists the 100 most recently updated conversations.
  New conversations accept optional `workspace_id` and up to 12 distinct
  `document_ids`. The legacy `document_id` field also accepts a single paper.
  `/answers` accepts `conversation_id`, uses its saved scope and bounded history,
  and saves each user/assistant pair atomically after successful generation.
  Concurrent replies return `409` if the conversation changed during generation.
  A selected paper that leaves the workspace blocks new replies until the
  paper rejoins the workspace. Standalone searches also accept repeated `document_ids`
  query parameters alongside an optional workspace filter.
- `GET/POST /workspaces`, `GET /workspaces/{workspace_id}`, and
  `PUT /workspaces/{workspace_id}/documents/{document_id}` — organize a
  local research library into persistent workspaces. Workspace retrieval
  isolation is available through the optional `workspace_id` filter on search
  and answers. Workspaces and Evidence explorer both support scope selection;
  comparison rejects papers outside the chosen workspace. Membership controls
  add/remove papers without deleting them from the library.
- `POST /comparisons` — accepts 2–12 distinct existing `document_ids` and
  retrieves passages for six research topics. This is passage comparison, not
  structured finding extraction or an assessment of experimental comparability.
- `POST /comparisons/structured` — accepts 2–6 papers and optional
  `workspace_id`. It uses the configured generation provider to extract exact
  excerpts for eight topics, including architecture, numerical outcomes and
  evaluation protocols. The model selects numeric IDs for server-generated
  windows. The server resolves the original excerpt and checks that reported
  values, signs, units and context labels occur in that window.
- `POST /comparison-runs` — starts a durable comparison and returns its ID.
  `GET /comparison-runs/{id}` returns status and the papers reviewed so far.
  `GET /comparison-runs` lists workspace-scoped history, and
  `POST /comparison-runs/{id}/cancel` stops further extraction and preserves
  previously saved findings.
- `GET /evidence-atlas` — reconstructs a graph from recent comparisons in
  the selected scope. Each relationship includes the source passage and page.
- `GET /evidence-atlas/{finding_id}/counterevidence` — resolves a finding within
  scope and retrieves candidate passages from other papers in that scope.
- `PUT /evidence-atlas/{finding_id}/reviews/{chunk_id}` — saves a researcher’s
  relationship assessment, experiment alignment judgment and note with both
  source snapshots.

Use **Evidence explorer** in the frontend for search and side-by-side comparisons
without a generation API key. Source links open at the cited PDF page when the
original is stored. Re-uploading an identical legacy PDF restores its source link
and page count without replacing embeddings. Missing matches do not prove that a
paper omits information.

Use **Comparison studio** to compare findings in a matrix, filter individual
claims, or navigate their paper, topic and passage relationships. Each excerpt
can open the source page, save its indexed passage or start an Assistant
question scoped to that paper. The studio keeps its results while you switch
views. Comparability checks flag conflicting or missing reported conditions.
Matching labels are candidates for review. The reproducibility checklist links
to indexed mentions of splits, seeds, optimization, compute and code availability.
The engine reviews a bounded keyword-selected sample from each paper.
**Export briefing** writes an extractive Markdown report with page and passage
provenance and the author-stated follow-up excerpts found in the sample.

The studio saves each paper as it completes. Run history can reopen partial or
completed results after a reload. The local service runs one comparison at a
time. If it stops during a run, the run becomes interrupted when its lease
expires, and completed papers remain available. Cancellation stops future work
and discards any in-flight result. The model request itself may finish locally.

**Evidence Atlas** draws a neighborhood around the selected node. Search and
filter by node or relationship type, expand or zoom the neighborhood, and
follow source links to Reader. The graph is rebuilt from saved comparison
excerpts for up to 30 papers from 50 recent runs in the selected scope.
Select **Library comparisons** for runs made outside a named workspace.
Dataset and metric edges reflect labels found in the excerpt. Topic labels
come from extraction and deserve review in the source.
**Potential disagreements** appears in Comparison Studio, its Markdown export,
and Evidence Atlas. It pairs explicit opposite comparisons only when both
excerpts report matching method, baseline, metric, dataset, task, split and
protocol labels. Both source passages are linked. Use the graph or Assistant
to review the methods and uncertainty. Coverage is limited to comparison
excerpts with sufficiently explicit wording and labels.

**Find counterevidence** ranks cross-paper passages with shared terms and
nearby qualifying phrases. Overlapping condition labels are shown separately
so the researcher can check whether the studies asked the same question.
Use **Assess passage** to record your conclusion separately from the candidate
ranking. The review stays in the comparison workspace and can be edited when
you revisit that finding.

**Reproducibility** distinguishes specific wording, general mentions and
details that were not located in the ranked passages. Open each checklist item
for the excerpt and a manual verification step. Export a Markdown Reproduction
Dossier with indexed page references and optional draft notes.

**Question coverage** uses four local research facets, with optional
model-proposed subquestions. Planning sends only the question to the configured
provider. Passage matching stays local. Expand a facet to inspect contributors,
save a passage, or open a scope-preserving Assistant draft. Match counts describe
retrieval coverage and need source review to establish support.

**Research directions** groups qualifying excerpts by theme and counts distinct
papers within the ranked sample. Edit the research question, hypothesis,
baselines, metrics and validation steps before exporting a plan. The candidate
directions require broader literature verification.

**Evidence packets** combine selected saved passages, notes and bibliography
metadata. Choose a briefing, literature review, technical comparison,
methodology overview, gap brief, reproduction dossier or question
investigation. Insert the outline or request a source-cited draft from the
configured provider using up to 16 snapshots. Insert citation IDs from the
source panel, then export to Markdown, escaped HTML, JSON or BibTeX. HTML
citations link to the corresponding snapshot. Revision checks protect
concurrent edits.

Use **Quick open** (Ctrl/⌘K) to navigate by view or paper title. The reader shows
the original PDF and indexed passages for the selected page. Its width slider
adjusts the split on wider screens. Citation links open the reader at the source page.
Choose multiple PDFs in **Library** to index them in order. The queue reports
imported, duplicate and failed items independently and lets you retry a failed
file. Use **Edit metadata** in Reader to correct bibliographic details and tags.
Library filtering includes DOI, venue and tags.
Use **Manage collections** in Library to create or rename a collection and
toggle paper membership. Choose a workspace to restrict the collection’s
eligible papers. Membership changes update the Library filter and keep the
original papers in the library.

## Generation providers

Gemini uses `GENERATION_PROVIDER=gemini`, `GEMINI_API_KEY` and `GEMINI_MODEL`.
For a downloaded model on a local Ollama server, use:

```dotenv
GENERATION_PROVIDER=ollama
GENERATION_MODEL=qwen3:8b
GENERATION_TIMEOUT_SECONDS=90
OLLAMA_REASONING_EFFORT=none
```

Open **Settings → AI Providers** to configure answering and structured
extraction independently. Select Ollama to discover installed models. Use
**Advanced connection** to change the loopback endpoint or request a larger
context from the local model. Leave the context field blank to use the Ollama
server default. For OpenAI,
Anthropic Claude, Gemini or an OpenAI-compatible service, enter the model
identifier and API key as needed. **Test connection** sends synthetic input
only. **Save provider** takes effect on the next request. Extraction uses the
answering profile until a separate extraction profile is saved.

Saved profiles override the environment defaults without changing `.env`.
Keys are encrypted in PostgreSQL using a key kept separately in
`.evidencerag/provider.key` with owner-only permissions. Keep that file private
and include it separately when backing up provider settings. The web interface
can replace a key and only receives an indication that one is stored.

OpenAI uses `GENERATION_PROVIDER=openai`, `GENERATION_MODEL` and
`GENERATION_API_KEY`. For a compatible server, select
`GENERATION_PROVIDER=openai-compatible` and set `GENERATION_BASE_URL` to
its API root, such as `http://127.0.0.1:11434/v1`. Use a model and server that
support Chat Completions JSON mode. For Claude's environment fallback, use
`GENERATION_PROVIDER=anthropic`, `GENERATION_MODEL` and `GENERATION_API_KEY`.
Ollama uses its `none` reasoning setting by default to keep extraction latency
down. Set `OLLAMA_REASONING_EFFORT` to a level supported by your local model if
the workflow benefits from more reasoning. For a launch or benchmark using
environment defaults, `OLLAMA_CONTEXT_TOKENS` applies the same context
override as the web field.
Cloud providers receive the question, supporting excerpts and bounded chat context.
Generation sends those fields in a structured payload and validates cited IDs
against evidence from the current request.
Search, comparison passages, the reader and the notebook work without a provider.

## Reading and annotating PDFs

New imports index each physical PDF page separately. Their search results and
citations point to a single page, even when blank pages occur in the source.
Existing passages retain their recorded page ranges and identifiers.
New imports also index complete rows from captioned, ruled tables when their
columns can be recovered. These passages include the original caption and
column names and link to the physical PDF page.
When a PDF provides a top-level outline, new passages retain that section
label in Reader and Assistant citations. The physical page remains the link
target. Older passages continue to use their stored page ranges.

Reader remembers the last page of each paper. Open a paper from Library to
resume there, or follow a citation to open its specific page. Library can
filter by reading status and sort by recent reading. The Reader's status
control lets you mark a paper finished or unread. `PATCH /documents/{id}/reading`
updates the page or status independently of the index and bibliographic metadata.

Reader renders the original PDF locally through a bundled PDF.js worker. It
supports fit-width zoom, selectable text and phrase search with page links.
Search uses the PDF’s text layer. Image-only pages need OCR before their text
can be found. **Open original PDF** opens the same source in the browser viewer.

Bookmark pages for quick return. Select text in an indexed passage and choose
**Highlight selection**, then add a note under **Page highlights**. The API
saves the exact selected text from the index. For chunks that span several
pages, the highlight is attached to the open page and the passage header gives
the full source range. Deleting a paper deletes its Reader bookmarks and notes.

## Embedding profiles

Each chunk records the embedding model and vector dimension used to create it.
Vector retrieval compares chunks from the active configured profile. After
changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS`, open **Search embeddings**
in Reader to see coverage and rebuild a paper. The rebuild uses existing
indexed text and retains the paper, source, passage IDs, and references. It
publishes replacement vectors together. You can cancel an active rebuild or
retry an interrupted one.

Apply new versioned migrations to an initialized database with
`.venv/bin/python -m app.db.migrations`. New installations use the bootstrap
command above, which also applies the migrations.

## Validation

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app scripts
EVIDENCERAG_INTEGRATION=1 .venv/bin/pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Run the versioned [synthetic benchmark](evaluation/corpus.json) against your
configured PostgreSQL server. It evaluates the actual keyword, vector and
hybrid retrievers and the answer API. It reports retrieval precision,
recall and reciprocal rank at four, required values, citation pages,
workspace isolation, abstention, and p50 and p95 latency. The database role
needs permission to create a schema. The benchmark creates an isolated
schema in a transaction and rolls it back.

Hybrid retrieval tries exact keyword matching first. When a natural-language
question has no exact lexical match, it can rank partial term matches within
the same scope. Quoted phrases, explicit OR and exclusions retain their
search semantics. The keyword column measures this fallback when enabled.

```bash
.venv/bin/python -m evaluation.run
.venv/bin/python -m evaluation.run --corpus reading-comprehension --json
```

The [reading comprehension benchmark](evaluation/reading_comprehension.json)
uses paraphrased findings from three published papers with original PDF page
anchors and section references. It checks whether individual numerical claims
cite the right passage, whether experimental comparisons disclose missing or
different conditions, and whether limitations and reproducibility details
are attributed to their sources. The default uses fixed embeddings and model
replies. Add `--live-embeddings` and `--live-provider` to evaluate the configured
models on the selected fixture. The JSON report includes the evaluated model
answers for review.

Assistant requests a constrained answer format from Ollama, Gemini and
native Claude and validates citations locally. OpenAI-compatible endpoints
can use JSON object mode. Citation validation confirms the passage
identifiers and their pages.
Newly indexed PDFs with extractable tables also preserve the caption, row
group and column-to-cell mapping on the physical page. Typed rows appear in
Reader and in Assistant evidence. Earlier passages remain available in their
original format.
For an explicit named-table question that identifies a metric and excludes
a condition, Assistant can validate the cited row and copy the cell's
measurement with its original units. It abstains when this check finds
ambiguous rows or an unsupported answer. The Assistant transcript displays
the matched columns and cell values next to their PDF source link.
General answers and named prose sections still require researcher review of
the linked passages.
For a named section compared with a table, the guarded path selects prose
about the requested row and metric and checks currency, percentages and
common scientific units against that excerpt. The PDF link retains the
original passage and page.
If generated comparison prose fails this check, Assistant can present
“Extracted source measurements” from the verified table cells and a single
unambiguous measurement in each requested section. Ambiguous sections still
produce abstention. Explicit statements that the supplied evidence lacks the
requested information are returned as abstentions.

The whole-PDF benchmark uses the [public NREL solar cost report](https://www.osti.gov/servlets/purl/2005540).
It imports the pinned PDF through the durable queue in a disposable schema,
checks a byte-identical source download, and measures retrieval and cited
answers across prose and tables. Use `--retrieval-only` for the embedding and
source checks without answer generation.

```bash
.venv/bin/python -m evaluation.pdf_benchmark /path/to/87303.pdf --retrieval-only
```

The report benchmark uses a fresh schema. Select an installed local model
with process-scoped settings for a live run.

```bash
GENERATION_PROVIDER=ollama GENERATION_MODEL=gemma4:e4b \
  .venv/bin/python -m evaluation.pdf_benchmark /path/to/87303.pdf
```

The browser suite runs the actual frontend and API in headless Chromium.
It provisions an isolated PostgreSQL schema and temporary upload directory,
then removes both. The suite generates its own two-page PDF and uses
deterministic model replies. Install Playwright's Chromium before the first
run, or set `PLAYWRIGHT_CHANNEL=chrome` to use an installed Google Chrome.

```bash
npm --prefix frontend exec -- playwright install chromium
.venv/bin/python -m evaluation.browser
```

Add `--screenshots /tmp/evidencerag-browser-audit` to capture Library, Reader,
Overview, Assistant, Comparison Studio, Claim Explorer, Evidence Atlas,
Reproducibility, Research directions, Evidence packets and AI Provider
Settings in light desktop, dark desktop and narrow layouts. The images use
only synthetic browser fixtures. To test real Ollama configuration and
Assistant citations through the browser, supply two installed model names.

```bash
EVIDENCERAG_BROWSER_OLLAMA_MODELS=gemma4:e4b,qwen3:8b \
  .venv/bin/python -m evaluation.browser
```

The library scale benchmark creates and removes a disposable schema. It
measures metadata listing and keyword, exact vector and hybrid retrieval
with synthetic 384-dimensional vectors and an optional ten-paper scope.
It includes local connection overhead and excludes PDF import, query
embedding, generation and rendering.

```bash
.venv/bin/python -m evaluation.library_scale --papers 500 --repetitions 20
```
