import { useEffect, useRef, useState } from "react";
import { api, type Document, type Provenance, type ReproductionDossier, type Workspace } from "./api";
import { SavePassage } from "./SavedEvidence";
import { categoryLabels, disclosureLabels, evidenceLabels, reproductionMarkdown } from "./reproductionDossier";

function exportDossier(dossier: ReproductionDossier, notes: string) {
  const url = URL.createObjectURL(new Blob([reproductionMarkdown(dossier, notes)], {type:"text/markdown;charset=utf-8"}));
  const a = document.createElement("a");
  a.href = url;
  a.download = `evidencerag-reproduction-${dossier.document_id}.md`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function DisclosureQuote({excerpt, source, match}: {excerpt: string; source: Provenance; match?: string}) {
  const pages = source.page_start === source.page_end ? `p. ${source.page_start}` : `pp. ${source.page_start}–${source.page_end}`;
  const start = match ? excerpt.indexOf(match) : -1;
  return <div className="finding-card">
    <blockquote>{match && start >= 0
      ? <>{excerpt.slice(0, start)}<mark>{match}</mark>{excerpt.slice(start + match.length)}</>
      : excerpt}</blockquote>
    <div className="finding-actions">
      <a href={`#paper=${source.document_id}&page=${source.page_start}`}>Open source · {pages}</a>
      <SavePassage id={source.chunk_id} />
    </div>
  </div>;
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
  const checks = result?.items.flatMap(item => item.disclosures ?? []) ?? [];
  const reported = checks.filter(check => check.status === "reported").length;
  const limitations = checks.filter(check => check.status === "limitation" || check.status === "mixed").length;
  const visibleItems = result?.items.filter(item => !status || item.status === status || (
    status === "limitations" && item.disclosures.some(check => check.status === "limitation" || check.status === "mixed")
  )) ?? [];
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
      {!!checks.length && <ul className="dossier-summary" aria-label="Components reviewed">
        <li><strong>{reported}</strong> details reported</li>
        <li><strong>{limitations}</strong> limitations or mixed statements</li>
        <li><strong>{checks.length - reported - limitations}</strong> not located</li>
      </ul>}
      <div className="comparison-filters"><label>Show <select value={status} onChange={e => setStatus(e.target.value)}>
        <option value="">All checklist items</option><option value="limitations">Stated limitations or mixed statements</option>
        {Object.entries(categoryLabels).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
      </select></label></div>
      {!visibleItems.length && <p className="muted">No checklist items match this filter.</p>}
      {visibleItems.map(item => <details key={item.label} className="check-row dossier-item">
          <summary><strong>{item.label}</strong> <span>{categoryLabels[item.status]}</span></summary>
          {item.excerpt && item.source && !item.disclosures.some(check => check.evidence.length) &&
            <DisclosureQuote excerpt={item.excerpt} source={item.source} />}
          <ul className="dossier-checks">{item.disclosures.map(check => <li key={check.label}>
            <div className="comparison-heading"><strong>{check.label}</strong><span>{disclosureLabels[check.status]}</span></div>
            {check.evidence.map(hit => <div key={hit.kind}>
              {check.status === "mixed" && <small>{evidenceLabels[hit.kind]}</small>}
              <DisclosureQuote excerpt={hit.excerpt} source={hit.source} match={hit.match} />
            </div>)}
          </li>)}</ul>
          <p>{item.verify}</p>
        </details>)}
      <label className="dossier-notes">Notes for export<textarea value={notes} rows={4} maxLength={5000} onChange={e => setNotes(e.target.value)} /></label>
    </section>}
  </div>;
}
