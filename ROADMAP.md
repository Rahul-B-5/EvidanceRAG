# EvidenceRAG implementation roadmap

The release gate for each journey is a real workflow with a provenance check,
an error-path check, and a record of what was actually verified. Current test and
delivery status live in [PROGRESS.md](PROGRESS.md).

| Journey | Working path | Remaining verification or implementation |
| --- | --- | --- |
| Library | Multi-file queue, duplicate handling, retries, metadata editing, tags, workspace collections, scope filters and source recovery | Re-embedding and persistent import jobs |
| Investigation | Hybrid search, fixed multi-paper scopes, page citations, streamed progress and cancel-before-commit | Automated browser upload-to-answer regression, evaluation of contextual follow-ups |
| Comparison | Matrix, source preview, evidence saving, durable partial results and condition checks | More experimental fields, confidence and support checks, representative corpus evaluation |
| Evidence Atlas | Persisted workspace graphs with paper, excerpt, topic, metric and dataset edges, plus two-source disagreement edges | Integrate notebook evidence, alternate layouts and larger-library testing |
| Disagreement | Scope candidates to matching reported setups and explicitly opposing statements, and persist separate human judgments | Evaluate false positives and expand coverage to other types of disagreement |
| Reproduction | Assess 24 components across 11 categories, cite access limitations and export a Markdown dossier | Verify artifact access and test experiments against documented instructions |
| Research directions | Scope-bounded limitation themes, evidence coverage, editable hypothesis and experiment plan, Markdown export | Cross-theme corpus analysis and wider literature verification |
| Deliverables | Saved notes, extractive comparison briefing, durable evidence packets, cited editable drafts, Markdown/HTML/JSON/BibTeX export | More briefing templates, integration with broader citation workflows and optional PDF export |
| Reader | Selectable PDF text, local phrase search, zoom, persistent bookmarks and indexed-text highlights with revisioned notes | Exact PDF-coordinate annotations, finer indexed page anchors and OCR |
| Everyday UX | Themes, keyboard palette and table views | Flagship visual review at desktop and narrow widths, accessibility and browser interaction regressions |
| Operations | Versioned additive migrations, local settings, PostgreSQL tests | Recovery and retention, safer ingestion lifecycle, model error/cancellation tests, quality and latency benchmarks |

## Dependency order

1. Finish and verify excerpt selection, numerical provenance and scope isolation.
2. Store research runs with provenance, bounded jobs and partial results. Reuse
   that data for durable claim lineage and the Evidence Atlas.
3. Add support assessment with explicit uncertainty, counterevidence retrieval,
   experiment alignment and research question coverage.
4. Add reproducibility dossiers, corpus-scoped research directions, and editable
   evidence packets. Integrate annotations, bibliography and local backups.
5. Verify the journeys on a public or synthetic corpus and the real desktop UI.
