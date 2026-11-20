# EvidenceRAG implementation roadmap

The release gate for each journey is a real workflow with a provenance check,
an error-path check, and a record of what was actually verified. Current test and
delivery status live in [PROGRESS.md](PROGRESS.md).

| Journey | Working path | Remaining verification or implementation |
| --- | --- | --- |
| Library | Import one PDF, index, search, attach to workspace, recover identical source | Multi-file progress, metadata editing, tags and collections, retry and re-embedding |
| Investigation | Scoped hybrid search and persistent Assistant with page citations | Explicit selection of several papers, streaming and cancellation, full browser upload-to-answer regression |
| Comparison | Matrix, source preview, evidence saving, durable partial results and condition checks | More experimental fields, confidence and support checks, representative corpus evaluation |
| Evidence Atlas | Inspect comparison-derived paper, topic and passage connections | Durable claims, typed evidence relationships, graph navigation, layout, zoom, and larger-library testing |
| Disagreement | Surface differing or missing experimental conditions | Compare opposing propositions under compatible conditions and retrieve candidate counterevidence |
| Reproduction | Find source mentions for five checklist items | Distinguish complete disclosures from mentions, extend fields and export a reproduction dossier |
| Research directions | Surface explicit follow-up wording in selected limitations | Corpus coverage analysis, hypothesis and experiment plan, broader verification status |
| Deliverables | Saved notes, Markdown notebook export, extractive comparison briefing | Editable research drafts and evidence packets with JSON, HTML and BibTeX where appropriate |
| Everyday UX | Themes, keyboard palette, split reader, table views | Flagship visual review at desktop and narrow widths, accessibility and browser interaction regressions |
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
