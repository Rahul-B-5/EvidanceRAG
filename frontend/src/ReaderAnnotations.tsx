import { useState } from "react";
import { api, type HighlightSelection, type Passage, type ReaderHighlight } from "./api";
import { SavePassage } from "./SavedEvidence";
import { pageLabel } from "./pageLabel";

export function AnnotatedPassage({passage, page, highlights, onHighlight}: {
  passage: Passage; page: number; highlights: ReaderHighlight[];
  onHighlight?: (selection: HighlightSelection) => Promise<boolean>;
}) {
  const [selection, setSelection] = useState<HighlightSelection | null>(null);
  const [saving, setSaving] = useState(false);
  const characters = Array.from(passage.text);
  const intervals: Array<{start: number; end: number}> = [];
  const anchors = highlights.filter(h => h.chunk_id === passage.chunk_id)
    .sort((a, b) => a.start_offset - b.start_offset);
  for (const anchor of anchors) {
    const start = anchor.start_offset;
    const end = anchor.end_offset;
    if (characters.slice(start, end).join("") !== anchor.quote) continue;
    const previous = intervals.at(-1);
    if (previous && start <= previous.end) previous.end = Math.max(previous.end, end);
    else intervals.push({start, end});
  }
  let offset = 0;

  function capture(element: HTMLParagraphElement) {
    const selected = window.getSelection();
    setSelection(null);
    if (!selected || selected.isCollapsed || selected.rangeCount !== 1) return;
    const range = selected.getRangeAt(0);
    if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) return;
    const prefix = range.cloneRange();
    prefix.selectNodeContents(element);
    prefix.setEnd(range.startContainer, range.startOffset);
    const start = Array.from(prefix.toString()).length;
    const quote = range.toString();
    const length = Array.from(quote).length;
    if (!quote.trim() || length > 2000) return;
    setSelection({chunk_id:passage.chunk_id, page, start_offset:start, end_offset:start + length});
  }

  async function save() {
    if (!selection || !onHighlight) return;
    setSaving(true);
    try {
      if (await onHighlight(selection)) setSelection(null);
    } finally {
      setSaving(false);
    }
  }

  return <article><small>{pageLabel(passage.page_start, passage.page_end)} · Passage {passage.chunk_id}</small>
    <p tabIndex={0} onMouseUp={e => capture(e.currentTarget)} onKeyUp={e => capture(e.currentTarget)}
      onTouchEnd={e => capture(e.currentTarget)}>
      {intervals.map(({start, end}) => {
        const leading = characters.slice(offset, start).join("");
        offset = end;
        return <span key={start}>{leading}<mark>{characters.slice(start, end).join("")}</mark></span>;
      })}{characters.slice(offset).join("")}
    </p>
    <div className="finding-actions">
      <SavePassage id={passage.chunk_id} />
      {selection && onHighlight && <button className="secondary" disabled={saving} onClick={save}>Highlight selection</button>}
    </div>
  </article>;
}

export function HighlightCard({documentId, highlight, update, remove}: {
  documentId: number; highlight: ReaderHighlight;
  update: (highlight: ReaderHighlight) => void; remove: (id: string) => void;
}) {
  const [note, setNote] = useState(highlight.note);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);

  async function change(deleting: boolean) {
    setBusy(true);
    setError("");
    try {
      if (deleting) {
        await api.deleteHighlight(documentId, highlight);
        remove(highlight.id);
      } else {
        update(await api.editHighlight(documentId, highlight, note));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update highlight.");
    } finally { setBusy(false); }
  }

  return <article className="reader-highlight">
    <blockquote>{highlight.quote}</blockquote>
    {!highlight.chunk_id && <small>The indexed passage is no longer linked.</small>}
    <form onSubmit={e => {e.preventDefault(); void change(false);}}>
      <label>Highlight note<textarea value={note} maxLength={4000} onChange={e => setNote(e.target.value)} rows={2} /></label>
      <div className="finding-actions">
        <button className="secondary" disabled={busy || note === highlight.note}>Save note</button>
        <button type="button" className="secondary danger" disabled={busy} onClick={() => setConfirmRemove(true)}>Remove highlight</button>
      </div>
    </form>
    {confirmRemove && <div className="finding-actions">
      <span>Remove this highlight and its note?</span>
      <button type="button" className="secondary danger" disabled={busy} onClick={() => change(true)}>Remove</button>
      <button type="button" className="secondary" disabled={busy} onClick={() => setConfirmRemove(false)}>Cancel</button>
    </div>}
    {error && <p role="alert">{error}</p>}
  </article>;
}
