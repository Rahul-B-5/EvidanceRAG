import { useEffect, useState } from "react";
import { api, type SavedPassage } from "./api";

export function SavePassage({id}: {id: number}) {
  const [state, setState] = useState<"idle" | "pending" | "saved">("idle");
  const [error, setError] = useState("");
  async function save() {
    setState("pending"); setError("");
    try {
      await api.savePassage(id);
      setState("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save passage.");
      setState("idle");
    }
  }
  return <span className="save-passage">
    <button className="secondary" disabled={state !== "idle"} onClick={() => void save()}>
      {state === "saved" ? "Saved" : state === "pending" ? "Saving…" : "Save passage"}
    </button>
    {error && <span role="alert">{error}</span>}
  </span>;
}

function NoteEditor({item, onSave}: {item: SavedPassage; onSave: (note: string) => void}) {
  const [note, setNote] = useState(item.note);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  async function update() {
    setBusy(true); setStatus("");
    try {
      const result = await api.updateNote(item.chunk_id, note);
      setStatus("Note saved.");
      onSave(result.note);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Unable to save note.");
    } finally {
      setBusy(false);
    }
  }
  return <form onSubmit={e => {e.preventDefault(); void update();}}>
    <label>Research note<textarea rows={3} maxLength={20000} value={note} onChange={e => setNote(e.target.value)} /></label>
    <button disabled={busy || note === item.note}>Save note</button><span role="status"> {status}</span>
  </form>;
}

function TagEditor({item, onSave}: {item: SavedPassage; onSave: (tags: string[]) => void}) {
  const [value, setValue] = useState(item.tags.join(", "));
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  async function update() {
    setBusy(true); setStatus("");
    try {
      const {tags} = await api.updatePassageTags(item.chunk_id, value.split(",").map(tag => tag.trim()).filter(Boolean));
      setValue(tags.join(", "));
      setStatus("Tags saved.");
      onSave(tags);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Unable to save tags.");
    } finally {
      setBusy(false);
    }
  }
  return <form className="notebook-tags" onSubmit={e => {e.preventDefault(); void update();}}>
    <label>Tags <small>Separate tags with commas</small>
      <input value={value} disabled={busy} maxLength={984} onChange={e => setValue(e.target.value)} />
    </label>
    <button disabled={busy || value === item.tags.join(", ")} className="secondary">Save tags</button>
    <span role="status">{status}</span>
  </form>;
}

export function SavedEvidence() {
  const [items, setItems] = useState<SavedPassage[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  useEffect(() => {
    let active = true;
    api.savedEvidence().then(result => {if (active) setItems(result.items);})
      .catch(e => {if (active) setError(e instanceof Error ? e.message : "Unable to load saved evidence.");});
    return () => {active = false;};
  }, []);

  async function exportNotes() {
    try {
      const {items: latest} = await api.savedEvidence();
      const sections = latest.map(p => [
        "## " + p.title.replace(/\s+/g, " "),
        `Pages ${p.page_start}–${p.page_end} · EvidenceRAG passage ${p.chunk_id}`,
        p.tags.length ? `Tags: ${p.tags.join(", ").replace(/[\\`*_{}\[\]<>|]/g, "\\$&")}` : "",
        p.passage.split("\n").map(line => "> " + line).join("\n"),
        p.note || "",
      ].filter(Boolean).join("\n\n"));
      const url = URL.createObjectURL(new Blob(["# Saved research evidence\n\n" + sections.join("\n\n")], {type:"text/markdown"}));
      const link = document.createElement("a");
      link.href = url;
      link.download = "evidencerag-notes.md";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    }
  }

  const tags = [...new Set(items?.flatMap(item => item.tags))].sort((a, b) => a.localeCompare(b));
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const visible = items?.filter(item => {
    const content = [item.title, item.passage, item.note, ...item.tags].join(" ").toLocaleLowerCase();
    return (!tag || item.tags.includes(tag)) && terms.every(term => content.includes(term));
  });
  function updateItem(id: number, changes: Partial<Pick<SavedPassage, "note" | "tags">>) {
    setItems(current => current?.map(item => item.chunk_id === id ? {...item, ...changes} : item) ?? null);
    if (changes.tags && !changes.tags.includes(tag) &&
        !items?.some(item => item.chunk_id !== id && item.tags.includes(tag))) setTag("");
  }

  return <div className="research-tools">
    {error && <p className="notice error" role="alert">{error}</p>}
    {!items && !error && <p role="status">Loading saved passages…</p>}
    {items?.length === 0 && <section className="panel empty">Save passages from Reader or Evidence & compare to build a research notebook.</section>}
    {!!items?.length && <section className="panel notebook-controls" aria-label="Filter saved evidence">
      <div className="research-controls">
        <label>Search saved evidence<input type="search" value={query} onChange={e => setQuery(e.target.value)} /></label>
        <label>Filter by tag<select value={tag} onChange={e => setTag(e.target.value)}>
          <option value="">All tags</option>
          {tags.map(item => <option key={item}>{item}</option>)}
        </select></label>
      </div>
      <div className="comparison-heading"><span role="status">{visible?.length} of {items.length} passages</span>
        <button className="secondary" onClick={() => void exportNotes()}>Export Markdown</button></div>
    </section>}
    {!!items?.length && visible?.length === 0 && <p className="notice">No passages match these filters.</p>}
    {visible?.map(p => <article className="panel saved-item" key={p.chunk_id}>
      <h2>{p.title}</h2>
      {p.source_exists ? <a href={`#paper=${p.document_id}&page=${p.page_start}`}>Pages {p.page_start}–{p.page_end}</a> : <p>Pages {p.page_start}–{p.page_end} · Source paper unavailable</p>}
      {!!p.tags.length && <ul className="assistant-source-tags" aria-label="Passage tags">
        {p.tags.map(item => <li className="tag" key={item}>{item}</li>)}
      </ul>}
      <blockquote>{p.passage}</blockquote>
      <NoteEditor item={p} onSave={note => updateItem(p.chunk_id, {note})} />
      <TagEditor item={p} onSave={tags => updateItem(p.chunk_id, {tags})} />
    </article>)}
  </div>;
}
