# EvidenceRAG implementation progress

## Completed and verified

- PostgreSQL/pgvector ingestion, content-addressed source storage, hybrid
  retrieval, evidence contexts, and citation validation.
- FastAPI document lifecycle, source delivery, safe deletion, conversations,
  workspace persistence, and provider boundary.
- Backward-compatible, idempotent schema initialization tested against the
  existing local database. Existing library remains at 2 documents and 34
  chunks after integration tests.
- Live API upload/retrieval/source/download/deletion and workspace workflows.
- `pytest -q`: 20 tests passing.

## Current limitation

- No Node/npm runtime is installed in the current environment, so the React +
  TypeScript frontend cannot be built or verified yet.
- `GEMINI_API_KEY` is not configured, so live generation correctly returns
  `503`; ingestion and retrieval remain fully usable.
- Backend milestone commit `1dcef99` is local only because GitHub rejected the
  available HTTPS credentials (`Invalid username or token`).

## Next implementation task

1. Install or make available a Node 20+ toolchain, scaffold the React +
   TypeScript frontend, and integrate it with the verified API contracts.
2. Implement structured cross-paper comparison and saved evidence/notes on
   top of workspace membership.
3. Add additional generation providers and integration tests when credentials
   or a local compatible model are configured.
