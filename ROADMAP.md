# EvidenceRAG implementation roadmap

The release gate for each journey is a real workflow with a provenance check,
an error-path check, and a record of what was actually verified. Current test and
delivery status live in [PROGRESS.md](PROGRESS.md).

| Journey | Working path | Remaining verification or implementation |
| --- | --- | --- |
| Library | Durable multi-file imports with restart recovery, metadata, workspace collections, reading status, related papers, source recovery and atomic embedding rebuilds | Broader library scale testing |
| Investigation | Hybrid search, fixed multi-paper scopes, explicit legacy scope recovery, citations to pages and passages, streamed progress and a guarded path for explicit metric and condition questions about named tables | Broader numerical and prose grounding, repeatable live abstention and corpus coverage |
| Comparison | Matrix, source preview, evidence saving, durable partial results and condition checks | More experimental fields, confidence and support checks, representative corpus evaluation |
| Claim Explorer | Persistent workspace-scoped excerpts, indexed search, revisioned human assessments, shared-label links, counterevidence, and Reader and Atlas navigation | More precise claim spans and a representative support evaluation |
| Evidence Atlas | Persisted claim, paper, method, metric, dataset, notebook and Reader annotation nodes, plus two-source shared-label and disagreement edges | Alternate layouts and larger-library testing |
| Disagreement | Scope candidates to matching reported setups and explicitly opposing statements, and persist separate human judgments | Evaluate false positives and expand coverage to other types of disagreement |
| Reproduction | Assess 24 components across 11 categories, cite access limitations and export a Markdown dossier | Verify artifact access and test experiments against documented instructions |
| Research directions | Topic-focused workspace sampling separates stated limitations and reported evaluations, with editable plans and dual-source Markdown export | Cross-theme corpus analysis and wider literature verification |
| Deliverables | Searchable notes, tags and Reader highlights scoped to workspace and collection, comparison briefings, durable evidence packets, cited drafts and Markdown/HTML/JSON/BibTeX exports | Citation managers and optional PDF export |
| Reader | Selectable PDF text, local phrase search, zoom, page resume, bookmarks, revisioned highlights, PDF outline labels, cited passage focus and typed table cells for newly indexed PDFs | Exact PDF-coordinate annotations and OCR |
| Everyday UX | Shared light and dark styles, keyboard palette, accessible mobile menu and six flagship screen screenshots with responsive checks | Wider assistive-technology testing and visual QA on secondary screens |
| Operations | Verified local launcher, additive migrations, encrypted web provider profiles, live model switching, PostgreSQL and browser suites, safe source lifecycle and local API host/origin policy | Live cloud-provider checks, larger corpus tests and retention |

## Dependency order

1. Finish and verify excerpt selection, numerical provenance and scope isolation.
2. Store research runs with provenance, bounded jobs and partial results. Reuse
   that data for durable claim lineage and the Evidence Atlas.
3. Add support assessment with explicit uncertainty, counterevidence retrieval,
   experiment alignment and research question coverage.
4. Add reproducibility dossiers, corpus-scoped research directions, and editable
   evidence packets. Integrate annotations, bibliography and local backups.
5. Verify the journeys on a public or synthetic corpus and the real desktop UI.
