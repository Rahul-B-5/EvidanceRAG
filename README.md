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
   npm install
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
- `DELETE /documents/{document_id}` — removes the document, its chunks, and its
  managed source file after the database transaction commits.
- `GET /search?query=...` — returns hybrid-retrieved evidence passages.
- `POST /answers` — creates a citation-validated answer from retrieved
  evidence. This requires `GEMINI_API_KEY`; search and ingestion do not.
- `POST /conversations` and `GET /conversations/{conversation_id}` — persist
  research-assistant conversation history and cited assistant responses.
- `GET/POST /workspaces`, `GET /workspaces/{workspace_id}`, and
  `PUT /workspaces/{workspace_id}/documents/{document_id}` — organize a
  local research library into persistent, source-isolated workspaces.

## Embedding profiles

Each chunk records the embedding model and vector dimension used to create it.
Vector retrieval only compares chunks from the active configured profile, so a
model change cannot silently compare incompatible embedding spaces. Reprocess
documents after changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS`.

Generation is provider-based. `GENERATION_PROVIDER=gemini` is the current
implementation; adding a local or cloud provider only requires another
`GenerationProvider` implementation.

## Validation

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app scripts
```
