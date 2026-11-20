import { useEffect, useRef, useState } from "react";
import { api, type CoverageMap, type Workspace } from "./api";
import type { FindingQuestion } from "./ComparisonStudio";
import { SavePassage } from "./SavedEvidence";

const statuses = {
  multiple_papers: "Matches across papers",
  single_paper: "One contributing paper",
  not_located: "No matching passages",
};

export function ResearchCoverage({workspaces, ask}: {workspaces: Workspace[]; ask: (question: FindingQuestion) => void}) {
  const [question, setQuestion] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [useProvider, setUseProvider] = useState(false);
  const [result, setResult] = useState<CoverageMap | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  async function map() {
    const controller = new AbortController();
    pending.current?.abort();
    pending.current = controller;
    setBusy(true);setError("");setResult(null);
    try {
      const response = await api.coverage(question.trim(), workspace, useProvider, controller.signal);
      if (!controller.signal.aborted) setResult(response);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to map this question.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <div className="research-tools">
    <form className="panel comparison-setup" onSubmit={e => {e.preventDefault();void map();}}>
      <label className="dossier-notes">Research question
        <textarea required minLength={8} maxLength={1200} disabled={busy} value={question} onChange={e => setQuestion(e.target.value)}
          placeholder="What approaches improve anomaly detection with limited labels?" rows={3} />
      </label>
      <div className="finding-actions">
        <label>Workspace <select disabled={busy} value={workspace} onChange={e => {setWorkspace(e.target.value);setResult(null);}}>
          <option value="">Entire library</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select></label>
        <label><input type="checkbox" disabled={busy} checked={useProvider} onChange={e => setUseProvider(e.target.checked)} /> Suggest subquestions with the configured provider</label>
      </div>
      {useProvider && <p className="muted">The planner sends the question to the configured model. Passage matching runs locally.</p>}
      <div><button disabled={busy || question.trim().length < 8}>{busy ? "Mapping the evidence…" : "Map question coverage"}</button></div>
    </form>
    {error && <p className="notice error" role="alert">{error}</p>}
    {result && <section className="panel">
      <h2>{result.question}</h2>
      <p>Matching passages show where to investigate. Open the sources to check whether they answer the subquestion.</p>
      {result.facets.map((facet, i) => <details className="check-row dossier-item" key={i}>
        <summary><strong>{facet.title}</strong> <span>{statuses[facet.status]}{facet.passages.length ? ` · ${facet.passages.length}` : ""}</span></summary>
        <p>{facet.question}</p>
        <button className="secondary" onClick={() => ask({
          workspaceId: workspace ? Number(workspace) : undefined,
          question: `${facet.question}\nResearch question: ${result.question}`,
        })}>Ask Assistant about this subquestion</button>
        {facet.passages.map(p => <article className="finding-card" key={p.chunk_id}>
          <strong>{p.title}</strong><blockquote>{p.excerpt}</blockquote>
          <div className="finding-actions"><a href={`#paper=${p.document_id}&page=${p.page_start}`}>Open source · p. {p.page_start}</a><SavePassage id={p.chunk_id} /></div>
        </article>)}
      </details>)}
    </section>}
  </div>;
}
