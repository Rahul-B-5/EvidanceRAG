import { lazy, Suspense, useEffect, useState, type CSSProperties } from "react";
import { api, type Document, type HighlightSelection, type Passage, type ReaderHighlight, type ReadingStatus, type ReadingUpdate } from "./api";
import { AnnotatedPassage, HighlightCard } from "./ReaderAnnotations";
import { MetadataEditor } from "./DocumentMetadata";
import { EmbeddingPanel } from "./EmbeddingPanel";
import { readingStatusLabels } from "./readingStatus";

const PdfViewer = lazy(() => import("./PdfViewer"));

export function Reader({document, initialPage = 1, workspace = "", remove, update, saveReading}: {
  document: Document; initialPage?: number; workspace?: string; remove: () => void; update: (paper: Document) => void;
  saveReading: (id: number, change: ReadingUpdate) => Promise<void>;
}) {
  const [page, setPage] = useState(initialPage);
  const [draft, setDraft] = useState(String(initialPage));
  const [width, setWidth] = useState(68);
  const [pdfPages, setPdfPages] = useState<number>();
  const [readingError, setReadingError] = useState("");
  const [savingStatus, setSavingStatus] = useState(false);
  const maximum = pdfPages ?? document.page_count ?? 100000;

  useEffect(() => {
    if (page > maximum || (document.has_stored_source && pdfPages === undefined)) return;
    let active = true;
    setReadingError("");
    saveReading(document.id, {page}).catch(() => {
      if (active) setReadingError("Unable to remember this page.");
    });
    return () => {active = false;};
  }, [document.id, document.has_stored_source, maximum, page, pdfPages, saveReading]);

  async function setReadingStatus(status: ReadingStatus) {
    setSavingStatus(true);
    setReadingError("");
    try {
      await saveReading(document.id, {status});
    } catch {
      setReadingError("Unable to change reading status.");
    } finally {
      setSavingStatus(false);
    }
  }

  function go(next: number) {
    if (!Number.isInteger(next) || next < 1 || next > maximum) {
      setDraft(String(page));
      return;
    }
    setPage(next);
    setDraft(String(next));
  }

  const source = api.sourceUrl(document.id);
  return <section className="panel reader-workspace">
    <div className="reader-heading"><div><h2>{document.title}</h2><p>{[document.venue, document.publication_year, document.doi].filter(Boolean).join(" · ") || document.filename}</p></div>
      <div className="finding-actions"><a href={`#claims-paper=${document.id}${workspace ? `&workspace=${workspace}` : ""}`}>Explore claims</a><MetadataEditor paper={document} update={update} /></div>
    </div>
    <div className="reader-toolbar">
      <form onSubmit={e => {e.preventDefault(); go(Number(draft));}}>
        <button type="button" className="secondary" disabled={page <= 1} onClick={() => go(page - 1)}>Previous</button>
        <label>Page <input type="number" min={1} max={maximum} value={draft} onChange={e => setDraft(e.target.value)} /></label>
        {(pdfPages ?? document.page_count) != null && <small>of {maximum}</small>}
        <button className="secondary" type="submit">Go</button>
        <button type="button" className="secondary" disabled={page >= maximum} onClick={() => go(page + 1)}>Next</button>
      </form>
      <label className="pane-size">PDF pane <input type="range" min={40} max={80} value={width} onChange={e => setWidth(Number(e.target.value))} /></label>
      <label className="reading-status-control">Reading status <select disabled={savingStatus} value={document.reading_status}
        onChange={e => void setReadingStatus(e.target.value as ReadingStatus)}>
        {Object.entries(readingStatusLabels).map(([status, label]) => <option key={status} value={status}>{label}</option>)}
      </select></label>
    </div>
    {readingError && <p className="reader-hint" role="status">{readingError}</p>}
    <div className="reader-panes" style={{"--reader-width": `${width}fr`, "--evidence-width": `${100 - width}fr`} as CSSProperties}>
      <div className="pdf-pane">
        {document.has_stored_source
          ? <><a href={`${source}#page=${page}`} target="_blank" rel="noreferrer">Open original PDF</a>
            <Suspense fallback={<p role="status">Loading PDF preview…</p>}>
              <PdfViewer url={source} page={page} go={go} onPageCount={count => {
                setPdfPages(count);
                if (page > count && count > 0) {
                  setPage(count);
                  setDraft(String(count));
                }
              }} />
            </Suspense></>
          : <p className="empty">The original PDF is missing. Import the identical PDF from Library to restore it.</p>}
      </div>
      <ReaderEvidence key={page} documentId={document.id} page={page} go={go} />
    </div>
    <div className="reader-settings">
      <EmbeddingPanel documentId={document.id} />
      <button className="secondary danger" onClick={remove}>Delete paper</button>
    </div>
  </section>;
}

function ReaderEvidence({documentId, page, go}: {documentId: number; page: number; go: (page: number) => void}) {
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [bookmarks, setBookmarks] = useState<number[] | null>(null);
  const [highlights, setHighlights] = useState<ReaderHighlight[]>([]);
  const [passageError, setPassageError] = useState("");
  const [annotationError, setAnnotationError] = useState("");
  const [bookmarkBusy, setBookmarkBusy] = useState(false);
  const bookmarked = bookmarks?.includes(page) ?? false;

  useEffect(() => {
    const controller = new AbortController();
    api.passages(documentId, page, controller.signal)
      .then(result => {if (!controller.signal.aborted) setPassages(result.passages);})
      .catch(err => {if (!controller.signal.aborted) setPassageError(err.message);});
    api.readerAnnotations(documentId, page, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      setBookmarks(result.bookmarks);
      setHighlights(result.highlights);
    }).catch(err => {if (!controller.signal.aborted) setAnnotationError(err.message);});
    return () => controller.abort();
  }, [documentId, page]);

  async function toggleBookmark() {
    setBookmarkBusy(true);
    setAnnotationError("");
    try {
      await api.setBookmark(documentId, page, !bookmarked);
      setBookmarks(current => bookmarked ? (current ?? []).filter(p => p !== page) : [...(current ?? []), page].sort((a, b) => a - b));
    } catch (err) {
      setAnnotationError(err instanceof Error ? err.message : "Unable to change bookmark.");
    } finally { setBookmarkBusy(false); }
  }

  async function highlight(selection: HighlightSelection) {
    setAnnotationError("");
    try {
      const saved = await api.createHighlight(documentId, selection);
      setHighlights(current => [...current, saved]);
      return true;
    } catch (err) {
      setAnnotationError(err instanceof Error ? err.message : "Unable to highlight selection.");
      return false;
    }
  }

  return <section className="reader-evidence" aria-label="Indexed page passages">
    <div className="reader-bookmarks">
      <button className="secondary" disabled={bookmarks === null || bookmarkBusy} onClick={toggleBookmark}>
        {bookmarked ? "Remove page bookmark" : "Bookmark page"}
      </button>
      {!!bookmarks?.length && <label>Bookmarks
        <select value="" onChange={e => go(Number(e.target.value))}>
          <option value="" disabled>Jump to page</option>
          {bookmarks.map(p => <option key={p} value={p}>Page {p}</option>)}
        </select>
      </label>}
    </div>
    <h3>Indexed passages · page {page}</h3>
    {annotationError && <p role="alert">{annotationError}</p>}
    {!!passages?.length && bookmarks !== null && <p className="reader-hint">Select text in a passage to highlight it.</p>}
    {passageError ? <p role="alert">{passageError}</p> : !passages ? <p role="status">Loading passages…</p>
      : !passages.length ? <p>No indexed text for this page.</p>
      : passages.map(p => <AnnotatedPassage key={p.chunk_id} passage={p} page={page} highlights={highlights}
        onHighlight={bookmarks === null ? undefined : highlight} />)}
    {!!highlights.length && <section aria-label="Page highlights">
      <h3>Page highlights</h3>
      {highlights.map(h => <HighlightCard key={h.id} documentId={documentId} highlight={h}
        update={updated => setHighlights(current => current.map(item => item.id === updated.id ? updated : item))}
        remove={id => setHighlights(current => current.filter(item => item.id !== id))} />)}
    </section>}
  </section>;
}
