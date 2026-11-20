import { useEffect, useState } from "react";
import { api, type ComparisonRun, type Document, type Finding, type StructuredComparison } from "./api";
import { SavePassage } from "./SavedEvidence";
import { EvidenceGraph } from "./EvidenceGraph";
import { comparisonBrief, followUpExcerpts } from "./comparisonBrief";

export type FindingQuestion = { documentId?: number; workspaceId?: number; question: string };
const labels: Record<string, string> = {
  methodology: "Methods", datasets: "Datasets", training: "Training", metrics: "Evaluation metrics",
  results: "Numerical findings", limitations: "Limitations", architecture: "Architecture", protocol: "Evaluation protocol",
  reported_difference: "Reported conditions differ", insufficient_context: "Insufficient context", candidate_match: "Candidate match · review conditions",
};
const findingKey = (f: Finding) => `${f.source.chunk_id}:${f.topic}:${f.quote}`;
const active = (run: ComparisonRun | null) => run?.status === "queued" || run?.status === "running";

function FindingCard({finding, ask}: {finding: Finding; ask: () => void}) {
  const {source, outcome, quote} = finding;
  return <article className="finding-card">
    {outcome.metric && <strong>{outcome.metric} · {outcome.value}</strong>}
    {finding.topic === "results" && !outcome.metric && <small>Result excerpt · numerical fields unavailable</small>}
    <blockquote>{quote}</blockquote>
    {outcome.metric && <dl>{Object.entries(outcome).filter(([key]) => key !== "metric" && key !== "value")
      .map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>}
    <div className="finding-actions">
      <a href={`#paper=${source.document_id}&page=${source.page_start}`}>Open source · p. {source.page_start}{source.page_end !== source.page_start ? `–${source.page_end}` : ""}</a>
      <SavePassage id={source.chunk_id} /><button className="secondary" onClick={ask}>Ask Assistant</button>
    </div>
  </article>;
}

export function ComparisonStudio({documents, workspaceId, ask}: {
  documents: Document[]; workspaceId?: number; ask: (question: FindingQuestion) => void;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const [result, setResult] = useState<StructuredComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<ComparisonRun[]>([]);
  const [run, setRun] = useState<ComparisonRun | null>(null);
  const [pollError, setPollError] = useState("");
  const [error, setError] = useState("");
  const [topicFilter, setTopicFilter] = useState("");
  const [layout, setLayout] = useState<"matrix" | "claims" | "graph">("matrix");
  const [paperFilter, setPaperFilter] = useState("");
  const titles = new Map(result?.papers.map(p => [p.document_id, p.title]));
  const selection = selected.filter(id => documents.some(d => d.id === id));
  const running = active(run);

  useEffect(() => {
    let cancelled = false;
    api.comparisonRuns(workspaceId).then(({runs}) => {
      if (!cancelled) setHistory(previous => [
        ...previous.filter(p => !runs.some(r => r.id === p.id)), ...runs,
      ]);
    }).catch(e => {if (!cancelled) setError(e instanceof Error ? e.message : "Unable to load run history.");});
    return () => {cancelled = true;};
  }, [workspaceId]);

  useEffect(() => {
    if (!run || !running) return;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout>;
    const id = run.id;
    async function poll() {
      try {
        const current = await api.comparisonRun(id, controller.signal);
        if (controller.signal.aborted) return;
        setRun(current);
        setPollError("");
        setResult(current.result.papers.length ? current.result : null);
        setHistory(runs => runs.map(r => r.id === id ? current : r));
        if (!active(current)) return;
      } catch {
        if (controller.signal.aborted) return;
        setPollError("Unable to refresh progress. Retrying…");
      }
      timeout = setTimeout(poll, 1500);
    }
    void poll();
    return () => {controller.abort();clearTimeout(timeout);};
  }, [run?.id, running]);

  async function compare() {
    setBusy(true);
    setError("");
    try {
      const started = await api.startComparison(selection, workspaceId);
      setHistory(items => [started, ...items]);
      setRun(started);
      setResult(null);
      setPollError("");
      setTopicFilter("");
      setPaperFilter("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Comparison failed.");
    } finally {
      setBusy(false);
    }
  }

  async function openRun(id: string) {
    if (!id) return;
    setBusy(true);
    setError("");
    try {
      const item = await api.comparisonRun(id);
      setTopicFilter("");
      setPaperFilter("");
      setRun(item);
      setResult(item.result.papers.length ? item.result : null);
      setHistory(items => items.map(r => r.id === id ? item : r));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to open comparison.");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (!run) return;
    setError("");
    try {
      await api.cancelComparison(run.id);
      await openRun(run.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to cancel this comparison.");
    }
  }

  function askFinding(f: Finding) {
    ask({documentId: f.source.document_id, workspaceId,
      question: `What context or qualifications does this paper give for the following excerpt?\n\n“${f.quote}”`});
  }

  function exportBrief(comparison: StructuredComparison) {
    const file = new Blob([comparisonBrief(comparison, labels)], {type: "text/markdown;charset=utf-8"});
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = "evidencerag-comparison.md";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const topics = result?.topics.filter(t => !topicFilter || t === topicFilter) ?? [];
  const followUps = result ? followUpExcerpts(result) : [];
  return <div className="research-tools">
    <section className="panel comparison-setup">
      <div><h2>Select papers</h2><p>Compare two to six papers using the configured generation provider.</p></div>
      {documents.length < 2 && <p className="muted">Add at least two papers to this scope.</p>}
      <fieldset aria-label="Papers to compare" disabled={busy || running}>
        {documents.map(d => <label key={d.id}><input type="checkbox" checked={selection.includes(d.id)}
          disabled={selection.length >= 6 && !selection.includes(d.id)}
          onChange={e => setSelected(e.target.checked ? [...selection, d.id] : selection.filter(id => id !== d.id))} /> {d.title}</label>)}
      </fieldset>
      <div className="finding-actions"><button disabled={busy || running || selection.length < 2} onClick={() => void compare()}>Run structured comparison</button><span>{selection.length} selected</span></div>
      {!!history.length && <label>Run history <select value={run?.id ?? ""} disabled={busy} onChange={e => void openRun(e.target.value)}>
        <option value="">Select a run</option>
        {history.map(item => <option key={item.id} value={item.id}>
          {new Date(item.created_at).toLocaleString()} · {item.titles.join(" / ")} · {item.status}
        </option>)}
      </select></label>}
    </section>
    {running && run && <div className="panel finding-actions">
      <p role="status">{result?.papers.length ?? 0} of {run.document_ids.length} papers reviewed</p>
      <progress max={run.document_ids.length} value={result?.papers.length ?? 0} aria-label="Comparison progress" />
      <button className="secondary" disabled={busy} onClick={() => void stop()}>Cancel after current request</button>
    </div>}
    {pollError && running && <p role="status">{pollError}</p>}
    {run && !running && <p role="status">Comparison {run.status}{run.error ? `. ${run.error}` : ""}</p>}
    {error && <p role="alert" className="notice error">{error}</p>}
    {result && <>
      <section className="panel">
        <div className="comparison-heading"><div><h2>Indexed source excerpts</h2><p>Topics and result context are model-selected. Inspect the excerpts to confirm they support the interpretation.</p></div>
          <div className="finding-actions">
            <button className="secondary" aria-pressed={layout === "matrix"} onClick={() => setLayout("matrix")}>Matrix</button>
            <button className="secondary" aria-pressed={layout === "claims"} onClick={() => setLayout("claims")}>Claim explorer</button>
            <button className="secondary" aria-pressed={layout === "graph"} onClick={() => setLayout("graph")}>Evidence graph</button>
            <button className="secondary" onClick={() => exportBrief(result)}>Export briefing</button>
          </div>
        </div>
        <div className="comparison-filters">
          <label>Topic <select value={topicFilter} onChange={e => setTopicFilter(e.target.value)}><option value="">All topics</option>{result.topics.map(t => <option value={t} key={t}>{labels[t]}</option>)}</select></label>
          {layout === "claims" && <label>Paper <select value={paperFilter} onChange={e => setPaperFilter(e.target.value)}><option value="">All selected papers</option>{result.papers.map(p => <option value={p.document_id} key={p.document_id}>{p.title}</option>)}</select></label>}
        </div>
        {layout === "matrix" ? <div className="comparison-scroll"><table className="comparison-matrix">
          <thead><tr><th scope="col">Topic</th>{result.papers.map(p => <th scope="col" key={p.document_id}>{p.title}<small>{p.reviewed_passages} passages reviewed · {p.findings.length} findings</small>{p.rejected_findings > 0 && <small>{p.rejected_findings} extraction items rejected</small>}</th>)}</tr></thead>
          <tbody>{topics.map(topic => <tr key={topic}><th scope="row">{labels[topic]}</th>{result.papers.map(p => {
            const matches = p.findings.filter(f => f.topic === topic);
            return <td key={p.document_id}>{matches.length ? matches.map(f => <FindingCard key={findingKey(f)} finding={f} ask={() => askFinding(f)} />)
              : <span className="muted">{p.reviewed_passages ? "No verified finding" : "No matching indexed passages"}</span>}</td>;
          })}</tr>)}</tbody></table></div>
          : layout === "graph" ? <EvidenceGraph papers={result.papers} topics={topics} labels={labels}
            inspect={(topic, paper) => {setTopicFilter(topic);setPaperFilter(String(paper));setLayout("claims");}} />
          : result.papers.filter(p => !paperFilter || String(p.document_id) === paperFilter).map(p => {
            const matches = p.findings.filter(f => topics.includes(f.topic));
            return <section key={p.document_id} className="claim-group"><h3>{p.title}</h3>
              {matches.length ? matches.map(f => <div key={findingKey(f)}><small>{labels[f.topic]}</small><FindingCard finding={f} ask={() => askFinding(f)} /></div>) : <p className="muted">No verified findings for this filter.</p>}
            </section>;
          })}
      </section>
      <section className="panel">
        <h2>Comparability checks</h2><p>Checks use the selected excerpts’ metric, dataset, task, split, protocol and baseline. Confirm matching definitions, units and conditions before ranking results.</p>
        {result.checks.map(check => <div className="claim-group" key={check.document_ids.join(":")}>
          <h3>{check.document_ids.map(id => titles.get(id)).join(" and ")}</h3>
          {!check.outcomes.length && <p className="muted">A numerical finding is missing for at least one paper.</p>}
          {check.outcomes.map((row, i) => <div className="check-row" key={i}>
            <strong>{labels[row.status]}</strong>
            <p>{row.left.outcome.metric}: {row.left.outcome.value} · {row.right.outcome.metric}: {row.right.outcome.value}</p>
            {!!row.differences.length && <p>Different labels: {row.differences.join(", ")}. Review the same setup before comparing scores.</p>}
            {!!row.missing.length && <p>Missing in at least one excerpt: {row.missing.join(", ")}.</p>}
          </div>)}
        </div>)}
      </section>
      <section className="panel">
        <h2>Author-reported follow-up</h2>
        <p>These candidate directions come from the selected papers. Check the broader literature before claiming a research gap.</p>
        {followUps.length ? followUps.map(({title, finding}) => <div className="claim-group" key={findingKey(finding)}>
          <h3>{title}</h3><FindingCard finding={finding} ask={() => askFinding(finding)} />
        </div>) : <p className="muted">No explicit follow-up wording matched in the selected limitation excerpts.</p>}
      </section>
      <section className="panel">
        <h2>Reproducibility checklist</h2><p>Keyword matches point to passages for manual review. A match signals a mention, and missing matches show where to look next.</p>
        {result.papers.map(p => <section className="claim-group" key={p.document_id}>
          <h3>{p.title}</h3>
          {(p.reproducibility ?? []).map(({item, mention}) => <details key={item} className="check-row">
            <summary>{item} · {mention ? "Mention located" : "No match in reviewed passages"}</summary>
            {mention ? <FindingCard finding={mention} ask={() => askFinding(mention)} />
              : <p>Review the full paper or supplementary materials for this item.</p>}
          </details>)}
        </section>)}
      </section>
    </>}
  </div>;
}
