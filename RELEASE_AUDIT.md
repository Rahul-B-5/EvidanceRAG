# Local release audit

Reviewed on 21 November 2026 against the final product completion brief.
This audit covers the supported single-user macOS deployment with one API
process, PostgreSQL with pgvector, and a loopback frontend. It does not certify
general scientific correctness or an internet-facing multi-user deployment.

## Feature and integration inventory

| Required journey | Implemented and verified behavior |
| --- | --- |
| Library and organization | Multi-PDF imports, metadata, workspaces, collections, reading status, durable processing jobs, retries, duplicate detection and atomic embedding rebuilds. |
| Reader | Original PDF rendering and download, physical pages, local text search, outline labels, zoom, resume, bookmarks, highlights, notes and citation focus on an exact indexed passage. |
| Assistant | Persistent scoped conversations, explicit recovery of legacy conversation scope, hybrid retrieval, cited answers, abstention, streamed progress, acknowledged cancellation and provider-failure retry. |
| Comparison Studio | Persistent multi-paper extraction runs, methods, datasets, architectures, metrics, numerical results and limitations, source previews, partial results, missing evidence and experimental-condition checks. |
| Claim Explorer | Persisted workspace claims, search and filters, provenance, evidence status, revisioned researcher assessments, related claims and handoffs to Reader, Assistant, Notebook and Atlas. |
| Evidence Atlas | Interactive typed relationships among papers, persisted claims, methods, metrics, datasets, saved evidence and Reader annotations. Relationships carry source references. Shared labels and candidate disagreements are review aids. |
| Scientific investigation | Counterevidence, opposing findings, comparability warnings, question coverage, corpus-scoped gaps, reproducibility assessments and editable investigation plans. Missing information is distinguished from an explicit reported limitation. |
| Research outputs | Saved evidence and notes, tags, comparison briefings, evidence packets, cited drafts and Markdown, HTML, JSON and BibTeX exports where applicable. |
| AI settings | Web configuration for Ollama, OpenAI, native Anthropic, Gemini and compatible endpoints. Separate answering and extraction profiles, connection tests, local model discovery and changes effective on the next request. |
| Everyday use | Shared light/dark design, narrow layouts, command palette, keyboard navigation, accessible form labels and recoverable loading/error states. |

The browser suite traverses these handoffs with imported disposable PDFs rather
than seeded production records. Provider settings are exercised through the web
and actual provider factories. Two installed Ollama models are also checked with
live answers and PDF citations. Cloud transports and error handling are covered
with controlled responses. Authenticated cloud calls have not been verified
because no cloud credentials were available for this release audit.

## Acceptance evidence

- PostgreSQL-enabled backend suite covers database transactions, scope isolation,
  import restart recovery, source lifecycle races, encrypted provider settings,
  citations, research workflows and malformed requests.
- Frontend unit checks and TypeScript production build cover export contracts,
  provenance, citation handoffs and application compilation.
- Chrome workflows cover upload, duplicates, malformed PDF handling, reading,
  annotation, saved evidence, scoped answers, comparisons, persisted claims,
  graph navigation, opposing findings, reproducibility, directions, coverage,
  briefing exports, model switching, cancellation and provider-failure retry.
  Screenshots cover the major screens in light desktop, dark desktop and
  390-pixel layouts. Reader captures wait for rendering after viewport changes.
- A separate process-restart smoke test preserved an imported PDF, bookmark and
  cited conversation in a disposable database schema.
- The supported launcher was exercised against the existing library through
  both `localhost:5173` and `127.0.0.1:5173`. It checks ports, database readiness,
  additive migrations and service readiness. Shutdown releases both listeners.
- Existing records were preserved. The current library contains three documents
  and 75 passages, already present when this completion effort began. A legacy
  source was recovered from byte-identical existing bytes without changing
  document metadata, chunks or embeddings. All three source hashes were checked.

Exact final run counts and delivery status are recorded at the top of
[PROGRESS.md](PROGRESS.md). The commands to reproduce the suites are in
[README.md](README.md#validation). Evaluations create isolated schemas and
temporary source directories. They do not reset the user's database.

## Scientific validation and its limits

Whole-PDF evaluations import pinned public sources through the durable queue and
verify downloaded originals byte for byte. The NREL report gate passed four of
four cases with both Qwen and Gemma. The latest Qwen run also passed after the
caption indexing change. The BERT paper gate passed five of five with Qwen.
These cases check table conditions, competing metrics, two-source references,
training settings, exact physical pages and abstention on unreported information.

Five published-paper excerpt cases passed with both local models, alongside
eight checks for comparability, contradiction false positives, gap attribution
and reproducibility extraction. The six-case synthetic corpus provides a
separate deterministic regression gate. Earlier failed evaluations remain in
the implementation history. The failures drove typed table evidence,
hierarchical headers, unit checks, scoped prose selection, context configuration
and removal of repeated caption notes from row search text.

Citation validation verifies IDs and page provenance. Stronger measurement
validation applies to explicit supported named-table/condition questions and
their requested prose sections. It rejects ambiguous associations and can
return labeled extracted measurements instead of unsupported generated prose.
General prose answers do not have equivalent semantic entailment guarantees.
Comparison extraction, counterevidence, gaps and reproducibility assessments
remain model-dependent or heuristic. A claim located in a paper is not proof
that the paper's conclusion is correct. Researchers must inspect the sources.

## Security, recovery and operating boundaries

- Credentials are encrypted in PostgreSQL using a separately stored owner-only
  local key. API responses expose credential presence, never the saved key.
  Browser storage does not retain credentials. Preserve the encryption key
  separately when backing up provider configuration.
- Host/origin policy, loopback model endpoint restrictions, bounded requests,
  source isolation and sanitized provider errors are tested. A configured cloud
  provider receives selected excerpts, the question and bounded chat context.
- Imports retain recoverable input and stage state. Duplicate recovery is
  non-destructive. Source deletion and reimport are serialized. Embedding
  rebuilds preserve the previous complete index until replacement succeeds.
- Explicit answer cancellation is acknowledged before the browser closes its
  stream. The cancellation registry is process-local. Multiple API workers
  require shared cancellation state or affinity. The supported launcher uses
  one API process.
- This is a trusted local application. Workspace isolation is a research scope
  boundary, not a substitute for authentication or multi-tenant authorization.
- Text PDFs are supported. OCR, exact PDF-coordinate annotations, citation
  manager synchronization and direct PDF report export are future extensions.
  Typed table improvements apply to new imports. Existing passages are not
  silently rewritten.
- Keyboard and responsive browser checks are covered. A complete independent
  screen-reader/accessibility audit and wider browser matrix remain unverified.

## Performance evidence

On this machine, a synthetic 500-paper/30,000-passage workload measured p95
listing at 13.5 ms, keyword retrieval at 52.7 ms, exact vector retrieval at
34.2 ms and hybrid retrieval at 104.2 ms. A ten-paper scope measured hybrid p95
at 12.7 ms. These measurements include connection overhead and exclude query
embedding, generation, PDF import and rendering. Twenty warm repetitions were
used. They are not a concurrent production-load guarantee.

A burst of 24 short four-page PDFs produced 96 passages in 2.3 seconds using
real embeddings and one import worker. Long, scanned, damaged or complex PDFs
can behave differently. Generation latency and quality depend on model,
hardware and context. The live report gates used an 8,192-token Ollama context.

## Launch the existing installation

Start the configured PostgreSQL server, then run from the repository directory

```bash
.venv/bin/python -m scripts.run_local
```

Open [EvidenceRAG](http://127.0.0.1:5173). Configure generation under
**Settings → AI Providers**. Start Ollama separately if using local generation.
Press Ctrl+C in the launcher terminal to stop the frontend and API. Clean
installation instructions are separate in README. Existing installations must
not rerun database initialization to resolve a connection issue.
