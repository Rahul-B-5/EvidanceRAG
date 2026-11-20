import { useRef, useState } from "react";
import { api, type Document } from "./api";

export function MetadataEditor({paper, update}: {paper: Document; update: (document: Document) => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const revision = useRef(paper.metadata_revision);
  const [title, setTitle] = useState(paper.title);
  const [authors, setAuthors] = useState(paper.authors.join("\n"));
  const [year, setYear] = useState(paper.publication_year?.toString() ?? "");
  const [doi, setDoi] = useState(paper.doi ?? "");
  const [venue, setVenue] = useState(paper.venue ?? "");
  const [tags, setTags] = useState(paper.tags.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function open() {
    revision.current = paper.metadata_revision;
    setTitle(paper.title);setAuthors(paper.authors.join("\n"));setYear(paper.publication_year?.toString() ?? "");
    setDoi(paper.doi ?? "");setVenue(paper.venue ?? "");setTags(paper.tags.join(", "));setError("");
    dialog.current?.showModal();
  }
  async function save() {
    setBusy(true); setError("");
    try {
      const changed = await api.editDocument(paper.id, {
        title, authors:authors.split("\n").map(a => a.trim()).filter(Boolean),
        publication_year:year ? Number(year) : null, doi:doi || null, venue:venue || null,
        tags:tags.split(",").map(t => t.trim()).filter(Boolean), metadata_revision:revision.current,
      });
      update(changed);
      dialog.current?.close();
    } catch(e) {
      setError(e instanceof Error ? e.message : "Unable to save metadata.");
    } finally {
      setBusy(false);
    }
  }
  return <>
    <button className="secondary" onClick={open}>Edit metadata</button>
    <dialog className="palette" aria-label="Edit paper metadata" ref={dialog}>
      <form className="metadata-form" onSubmit={e => {e.preventDefault();void save();}}>
        <h2>Edit paper metadata</h2>
        <label>Title<input required autoFocus value={title} maxLength={300} disabled={busy} onChange={e => setTitle(e.target.value)} /></label>
        <label>Authors, one per line<textarea rows={3} value={authors} disabled={busy} onChange={e => setAuthors(e.target.value)} /></label>
        <div className="metadata-grid">
          <label>Year<input type="number" min={1000} max={3000} value={year} disabled={busy} onChange={e => setYear(e.target.value)} /></label>
          <label>Venue<input value={venue} maxLength={200} disabled={busy} onChange={e => setVenue(e.target.value)} /></label>
        </div>
        <label>DOI<input value={doi} maxLength={220} disabled={busy} onChange={e => setDoi(e.target.value)} /></label>
        <label>Tags, separated by commas<input value={tags} disabled={busy} onChange={e => setTags(e.target.value)} /></label>
        {error && <p role="alert" className="notice error">{error}</p>}
        <div className="finding-actions">
          <button disabled={busy || !title.trim()}>Save metadata</button>
          <button type="button" className="secondary" disabled={busy} onClick={() => dialog.current?.close()}>Cancel</button>
        </div>
      </form>
    </dialog>
  </>;
}
