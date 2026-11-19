# EvidenceRAG

EvidenceRAG is a local-first, evidence-grounded research library for PDF
papers. It extracts papers, stores content-addressed source copies, indexes
hybrid keyword/vector evidence, and returns source-linked answers.

## Run locally

1. Create `.env` from `.env.example` and set your local PostgreSQL credentials.
   The default local PostgreSQL port is `5433`.
2. Apply the idempotent schema upgrade (it preserves existing documents and
   embeddings):

   ```bash
   .venv/bin/python scripts/init_db.py
   ```

3. Start the API:

   ```bash
   .venv/bin/uvicorn app.api.main:app --reload
   ```

4. In another terminal, start the React frontend (Node 20+):

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.
The application is served at `http://127.0.0.1:5173` and uses the local API at
`http://127.0.0.1:8000` by default. Set `VITE_API_URL` to change that address.

## Core endpoints

- `GET /health` — checks database reachability.
- `GET /documents` — lists library metadata and chunk counts.
- `GET /documents/{document_id}` — returns document metadata and processing status.
- `POST /documents` — imports one PDF as multipart field `file`.
- `GET /documents/{document_id}/source` — serves a persisted original PDF.
- `GET /documents/{document_id}/passages?page=...` — lists indexed chunks intersecting the page.
- `DELETE /documents/{document_id}` — removes the document, its chunks, and its
  managed source file after the database transaction commits.
- `GET /search?query=...` — returns hybrid-retrieved evidence passages.
- `POST /answers` — creates an answer with evidence citations using the configured provider.
- `GET /saved-evidence` and `PUT/PATCH /saved-evidence/{chunk_id}` — list and save
  provenance snapshots, and edit passage notes. Saved evidence exports to Markdown.
- `POST /conversations` and `GET /conversations/{conversation_id}` — persist
  research-assistant conversation history and cited assistant responses.
- `GET /conversations` — lists the 100 most recently updated conversations.
  New conversations accept optional `workspace_id` or `document_id` scope.
  `/answers` accepts `conversation_id`, uses its saved scope and bounded history,
  and saves each user/assistant pair atomically after successful generation.
  Concurrent replies return `409` if the conversation changed during generation.
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

Use **Evidence explorer** in the frontend for search and side-by-side comparisons
without a generation API key. Source links open at the cited PDF page when the
original is stored. Re-uploading an identical legacy PDF restores its source link
and page count without replacing embeddings. Missing matches do not prove that a
paper omits information.

Use **Quick open** (Ctrl/⌘K) to navigate by view or paper title. The reader shows
the original PDF and indexed passages for the selected page. Its width slider
adjusts the split on wider screens. Citation links open the reader at the source page.

## Generation providers

Gemini uses `GENERATION_PROVIDER=gemini`, `GEMINI_API_KEY` and `GEMINI_MODEL`.
For a downloaded model on a local Ollama server, use:

```dotenv
GENERATION_PROVIDER=ollama
GENERATION_MODEL=qwen3:8b
GENERATION_TIMEOUT_SECONDS=90
```

OpenAI uses `GENERATION_PROVIDER=openai`, `GENERATION_MODEL` and
`GENERATION_API_KEY`. For a compatible server, select
`GENERATION_PROVIDER=openai-compatible` and set `GENERATION_BASE_URL` to
its API root, such as `http://127.0.0.1:11434/v1`. Use a model and server that
support Chat Completions JSON mode. Restart the API after configuration changes.
Cloud providers receive the question, supporting excerpts and bounded chat context.
Search, comparison passages, the reader and the notebook work without a provider.

## Embedding profiles

Each chunk records the embedding model and vector dimension used to create it.
Vector retrieval only compares chunks from the active configured profile, so a
model change cannot silently compare incompatible embedding spaces. Reprocess
documents after changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS`.

Apply new versioned migrations to an initialized database with
`.venv/bin/python -m app.db.migrations`. New installations use the bootstrap
command above, which also applies the migrations.

## Validation

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app scripts
EVIDENCERAG_INTEGRATION=1 .venv/bin/pytest -q
```
