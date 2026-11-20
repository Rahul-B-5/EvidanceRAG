import { useEffect, useState, type CSSProperties } from "react";
import { api, type Document, type Passage } from "./api";
import { SavePassage } from "./SavedEvidence";
import { MetadataEditor } from "./DocumentMetadata";

export function Reader({document, initialPage = 1, remove, update}: {
  document: Document; initialPage?: number; remove: () => void; update: (paper: Document) => void;
}) {
  const [page, setPage] = useState(initialPage);
  const [draft, setDraft] = useState(String(initialPage));
  const [width, setWidth] = useState(68);
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [error, setError] = useState("");
  const maximum = document.page_count ?? 100000;
  useEffect(() => {
    const controller = new AbortController();
    setPassages(null);
    setError("");
    api.passages(document.id, page, controller.signal)
      .then(result => {if (!controller.signal.aborted) setPassages(result.passages);})
      .catch(err => {if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Unable to load passages.");});
    return () => controller.abort();
  }, [document.id, page]);

  function go(next: number) {
    if (!Number.isInteger(next) || next < 1 || next > maximum) {
      setDraft(String(page));
      return;
    }
    setPage(next);
    setDraft(String(next));
  }

  const source = `${api.sourceUrl(document.id)}#page=${page}`;
  return <section className="panel reader-workspace">
    <div className="reader-heading"><div><h2>{document.title}</h2><p>{[document.venue, document.publication_year, document.doi].filter(Boolean).join(" · ") || document.filename}</p></div>
      <div className="finding-actions"><MetadataEditor paper={document} update={update} /><button className="secondary danger" onClick={remove}>Delete paper</button></div>
    </div>
    <div className="reader-toolbar">
      <form onSubmit={e => {e.preventDefault(); go(Number(draft));}}>
        <button type="button" className="secondary" disabled={page <= 1} onClick={() => go(page - 1)}>Previous</button>
        <label>Page <input type="number" min={1} max={maximum} value={draft} onChange={e => setDraft(e.target.value)} /></label>
        <button className="secondary" type="submit">Go</button>
        <button type="button" className="secondary" disabled={page >= maximum} onClick={() => go(page + 1)}>Next</button>
      </form>
      <label className="pane-size">PDF pane <input type="range" min={40} max={80} value={width} onChange={e => setWidth(Number(e.target.value))} /></label>
    </div>
    <div className="reader-panes" style={{"--reader-width": `${width}fr`, "--evidence-width": `${100 - width}fr`} as CSSProperties}>
      <div className="pdf-pane">
        {document.has_stored_source
          ? <><a href={source} target="_blank" rel="noreferrer">Open original PDF</a><iframe key={source} title={`PDF: ${document.title}, page ${page}`} src={source} /></>
          : <p className="empty">The original PDF is missing. Import the identical PDF from Library to restore it.</p>}
      </div>
      <section className="reader-evidence" aria-label="Indexed page passages">
        <h3>Indexed passages · page {page}</h3>
        {error ? <p role="alert">{error}</p> : !passages ? <p role="status">Loading passages…</p> : !passages.length ? <p>No indexed text for this page.</p>
          : passages.map(p => <article key={p.chunk_id}><small>Pages {p.page_start}–{p.page_end} · Passage {p.chunk_id}</small><p>{p.text}</p><SavePassage id={p.chunk_id} /></article>)}
      </section>
    </div>
  </section>;
}
