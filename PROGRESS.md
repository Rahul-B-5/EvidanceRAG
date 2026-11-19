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

## Outstanding

1. Implement structured comparison with findings tied to exact quotations from provided passages. Add explicit missing-information and comparability judgments. Verify with synthetic papers and the local provider.
2. Build claim exploration, contradiction detection, reproducibility analysis, gap exploration, provenance graph and briefings on that verified result format.
3. Extend the notebook with tags, collections, annotations and bibliography export. Add browser coverage for save, edit, reopen and export. Add source view smoke coverage using a synthetic PDF.
4. Add retrieval and answer evaluation fixtures, quality/latency reporting and automated browser regressions. Identifier validation does not establish factual entailment.
5. Harden ingestion lifecycle, source cleanup races, legacy conversation scope backfill and re-embedding. Upgrade the local Node runtime from Node 20 to a supported release when convenient.

Keep private PDFs, environment files and generated artifacts out of Git. Development and browser verification are local. Live cloud verification is optional until credentials are configured.
