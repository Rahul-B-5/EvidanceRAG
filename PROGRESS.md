# EvidenceRAG implementation progress

## Current checkpoint — 2026-11-20 (supersedes historical notes below)

- Branch `main`; GitHub authentication works. Commits through `4b4d14e` were
  pushed. Node/npm is installed at `/opt/homebrew/opt/node@20/bin`; Node 20 is
  deprecated and should be upgraded before production deployment.
- Python suite: 32 tests passing; React/Vite production build passes.
- Browser-verified dashboard, evidence search and comparison against the actual
  library: 2 papers / 34 chunks; search returns five passages; comparison loads
  both existing papers. No existing private records were modified in these checks.
- Comparison now rejects missing/duplicate/nonpositive IDs and preserves titles
  when no passages match. Earlier tests guessed IDs [1,2], incorrectly treating
  one nonexistent document as missing evidence. This is fixed.
- Duplicate upload restores source paths/page counts without re-embedding.
  Unit tests cover recovery, changed source bytes and corrupted stored files.
  Existing library source paths have not been backfilled.

### Remaining work (product is not complete)

Workspace-scoped keyword/vector/hybrid retrieval and answers now accept
`workspace_id`; SQL filters candidates before ranking. Four isolation tests,
including an opt-in PostgreSQL test with automatically rolled-back fixtures,
passed. This is query scoping, not multi-user authorization. The frontend and
comparison endpoint still need workspace scope integration.
Conversation records exist, but the UI is single-turn and the backend does not
use conversation context. Message-pair persistence is not atomic. Only Gemini
is implemented and no live generation was verified without a configured key.
Status columns exist, but ingestion is synchronous without a job lifecycle.

Comparison retrieves topic passages; it does not extract structured findings,
assess comparability or detect contradictions. Reference-section matches can
rank too highly. Citation IDs are checked syntactically, not for entailment.
Saved evidence, notes, metadata editing, re-embedding, collections, graph, gap
analysis, reproducibility analysis, briefs and clustering remain unfinished.
Evaluation datasets and automated browser regressions are also missing.
Source-file deletion needs concurrency/recovery hardening; migrations need
version tracking. The current dark theme uses inversion and needs replacement.

### Exact next implementation task

Wire the workspace retrieval filter into the frontend and comparisons, including
missing workspace validation. Then wire workspace
membership and scoped conversations into the UI, make message writes atomic,
and add bounded conversation context. Follow with additional providers and
structured research analysis. Keep `.env`, private PDFs and generated build
files out of Git. See `git log -1` for the commit containing this checkpoint.

Latest verification: 35 unit tests pass, one database integration test is skipped
by default. `EVIDENCERAG_INTEGRATION=1 .venv/bin/pytest tests/test_workspace_integration.py`
passes against local PostgreSQL. Evidence explorer/source recovery was pushed as
`d556304`; the following scope commit includes this record.

## Historical checkpoint (outdated)

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
