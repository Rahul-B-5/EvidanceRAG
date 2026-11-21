# EvidenceRAG implementation roadmap

The release gate for each journey is a real workflow with a provenance check,
an error-path check, and a record of what was actually verified. Current test and
delivery status live in [PROGRESS.md](PROGRESS.md).

The required local product journeys are implemented and integrated. The final
[release audit](RELEASE_AUDIT.md) distinguishes verified behavior from scientific
and operating limits. The final column below tracks future extensions and wider
verification, rather than promising that each item is part of this local release.

| Journey | Working path | Future extensions and wider verification |
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
| Everyday UX | Shared light and dark styles, keyboard palette, accessible mobile menu and responsive screenshots across the main research journey | Wider assistive-technology testing and browser coverage for secondary error paths |
| Operations | Verified local launcher, additive migrations, encrypted web provider profiles, live model switching, PostgreSQL and browser suites, safe source lifecycle and local API host/origin policy | Live cloud-provider checks, concurrent loads, whole-library ingest scale and retention |

## Order for future development

1. Expand whole-paper grounding evaluation across disciplines, table formats,
   legacy passages and repeated model runs. Keep source verification visible.
2. Verify authenticated cloud accounts when credentials are available and test
   concurrent long-PDF imports, retrieval and generation under realistic loads.
3. Complete independent accessibility and wider-browser reviews before widening
   the supported deployment beyond the current local workflow.
4. Prioritize optional OCR, coordinate annotations and external citation-manager
   integrations based on research needs. Preserve existing evidence provenance.
5. Design shared cancellation and authenticated authorization before supporting
   multiple API workers or remote multi-user deployments.
