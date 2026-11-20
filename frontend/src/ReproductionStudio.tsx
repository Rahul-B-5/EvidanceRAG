import { useEffect, useRef, useState } from "react";
import { api, type Document, type ReproductionDossier, type Workspace } from "./api";
import { SavePassage } from "./SavedEvidence";

const labels = {
  specific_detail: "Specific wording located",
  mention: "General mention located",
  not_located: "Not located in reviewed passages",
};

function exportDossier(dossier: ReproductionDossier, notes: string) {
  const clean = (text: string) => text.replace(/[<>&]/g, char => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[char] ?? char);
  const sections = [
    "# Reproduction Dossier",
    `## ${clean(dossier.title.replace(/\s+/g, " "))}`,
    "Targeted scan of ranked passages. Check original pages and supplementary material before reproducing the study.",
  ];
  for (const item of dossier.items) {
    sections.push(`### ${item.label}`, labels[item.status]);
    if (item.excerpt && item.source) {
      sections.push(`> ${clean(item.excerpt)}`,
        `Paper ${dossier.document_id} · pages ${item.source.page_start}–${item.source.page_end} · passage ${item.source.chunk_id}`);
    }
    sections.push(`Verify: ${item.verify}`);
  }
  if (notes.trim()) sections.push("## Researcher notes", clean(notes));
  const url = URL.createObjectURL(new Blob([sections.join("\n\n") + "\n"], {type:"text/markdown;charset=utf-8"}));
  const a = document.createElement("a");
  a.href = url;
  a.download = `evidencerag-reproduction-${dossier.document_id}.md`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ReproductionStudio({documents, workspaces}: {documents: Document[]; workspaces: Workspace[]}) {
  const [workspace, setWorkspace] = useState("");
  const [paper, setPaper] = useState("");
  const [members, setMembers] = useState<number[] | null>(null);
  const [result, setResult] = useState<ReproductionDossier | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (!workspace) return;
    let active = true;
    api.workspace(Number(workspace)).then(w => {if (active) setMembers(w.documents.map(d => d.id));})
      .catch(e => {if (active) setError(e instanceof Error ? e.message : "Unable to load workspace papers.");});
    return () => {active = false;};
  }, [workspace]);

  const scoped = workspace ? documents.filter(d => members?.includes(d.id)) : documents;
  async function assess() {
    if (!scoped.some(d => String(d.id) === paper)) return;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setBusy(true); setError(""); setResult(null); setStatus("");
    try {
      const dossier = await api.reproduction(paper, workspace, controller.signal);
      if (!controller.signal.aborted) setResult(dossier);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to assess this paper.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <div className="research-tools">
    <form className="panel comparison-setup" onSubmit={e => {e.preventDefault(); void assess();}}>
      <div className="atlas-toolbar dossier-controls">
        <label>Workspace<select value={workspace} disabled={busy} onChange={e => {
          setWorkspace(e.target.value);setPaper("");setMembers(null);setResult(null);setError("");setNotes("");
        }}>
          <option value="">Entire library</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select></label>
        <label>Paper<select value={paper} disabled={busy || (!!workspace && members === null)} onChange={e => {
          setPaper(e.target.value);setResult(null);setError("");setNotes("");
        }}>
          <option value="">Select a paper</option>{scoped.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
        </select></label>
      </div>
      <div><button disabled={busy || !paper}>{busy ? "Checking indexed passages…" : "Assess reproducibility"}</button></div>
    </form>
    {error && <p role="alert" className="notice error">{error}</p>}
    {result && <section className="panel">
      <div className="comparison-heading">
        <div><h2>{result.title}</h2><p>Review the linked wording and verify details in the paper or supplement.</p></div>
        <button className="secondary" onClick={() => exportDossier(result, notes)}>Export Reproduction Dossier</button>
      </div>
      <div className="comparison-filters"><label>Show <select value={status} onChange={e => setStatus(e.target.value)}>
        <option value="">All checklist items</option>{Object.entries(labels).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
      </select></label></div>
      {result.items.filter(item => !status || item.status === status).map(item => <details key={item.label} className="check-row dossier-item">
        <summary><strong>{item.label}</strong> <span>{labels[item.status]}</span></summary>
        {item.excerpt && item.source && <article className="finding-card">
          <blockquote>{item.excerpt}</blockquote>
          <div className="finding-actions">
            <a href={`#paper=${item.source.document_id}&page=${item.source.page_start}`}>Open source · p. {item.source.page_start}</a>
            <SavePassage id={item.source.chunk_id} />
          </div>
        </article>}
        <p>{item.verify}</p>
      </details>)}
      <label className="dossier-notes">Notes for export<textarea value={notes} rows={4} maxLength={5000} onChange={e => setNotes(e.target.value)} /></label>
    </section>}
  </div>;
}
