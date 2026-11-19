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

function NoteEditor({item}: {item: SavedPassage}) {
  const [note, setNote] = useState(item.note);
  const [saved, setSaved] = useState(item.note);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  async function update() {
    setBusy(true); setStatus("");
    try {
      const result = await api.updateNote(item.chunk_id, note);
      setSaved(result.note);
      setStatus("Note saved.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Unable to save note.");
    } finally {
      setBusy(false);
    }
  }
  return <form onSubmit={e => {e.preventDefault(); void update();}}>
    <label>Research note<textarea rows={3} maxLength={20000} value={note} onChange={e => setNote(e.target.value)} /></label>
    <button disabled={busy || note === saved}>Save note</button><span role="status"> {status}</span>
  </form>;
}

export function SavedEvidence() {
  const [items, setItems] = useState<SavedPassage[] | null>(null);
  const [error, setError] = useState("");
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
        p.passage.split("\n").map(line => "> " + line).join("\n"),
        p.note || "",
      ].join("\n\n"));
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

  return <div className="research-tools">
    {error && <p className="notice error" role="alert">{error}</p>}
    {!items && !error && <p role="status">Loading saved passages…</p>}
    {items?.length === 0 && <section className="panel empty">Save passages from Reader or Evidence & compare to build a research notebook.</section>}
    {!!items?.length && <div><button className="secondary" onClick={() => void exportNotes()}>Export Markdown</button></div>}
    {items?.map(p => <article className="panel saved-item" key={p.chunk_id}>
      <h2>{p.title}</h2>
      {p.source_exists ? <a href={`#paper=${p.document_id}&page=${p.page_start}`}>Pages {p.page_start}–{p.page_end}</a> : <p>Pages {p.page_start}–{p.page_end} · Source paper unavailable</p>}
      <blockquote>{p.passage}</blockquote><NoteEditor item={p} />
    </article>)}
  </div>;
}
