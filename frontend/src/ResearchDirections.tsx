import { useEffect, useState } from "react";
import { api, type DirectionSource, type InvestigationPlan, type ResearchDirections, type Workspace } from "./api";
import type { FindingQuestion } from "./ComparisonStudio";
import { SavePassage } from "./SavedEvidence";
import { sourceLink } from "./sourceLink";

const fields: Array<[keyof InvestigationPlan, string]> = [
  ["question", "Research question"],
  ["hypothesis", "Testable hypothesis"],
  ["baseline", "Baselines and controls"],
  ["metrics", "Primary metrics"],
  ["validation", "Validation steps"],
];

function exportPlan(direction: ResearchDirections["directions"][number], plan: InvestigationPlan) {
  const plain = (s: string) => s.replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c] ?? c));
  const cite = (p: DirectionSource) => [
    `### ${plain(p.title.replace(/\s+/g, " "))}`,
    `> ${plain(p.excerpt)}`,
    `Paper ${p.document_id} · pages ${p.page_start}–${p.page_end} · passage ${p.chunk_id}`,
  ];
  const sections = [
    "# Research investigation plan",
    `## ${direction.title}`,
    "Candidate direction based on the reviewed local scope. Verify novelty in a wider literature search.",
    ...fields.flatMap(([key, label]) => [`### ${label}`, plain(plan[key].trim() || "To be specified.")]),
    "## Author-reported limitations and follow-ups",
    ...direction.evidence.flatMap(cite),
    "## Reported coverage of this theme",
    ...(direction.coverage.length ? direction.coverage.flatMap(cite) : ["No explicit coverage was located in the sampled passages."]),
  ];
  const url = URL.createObjectURL(new Blob([sections.join("\n\n") + "\n"], {type: "text/markdown;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url; link.download = `evidencerag-plan-${direction.id}.md`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function SourceCard({source, workspace}: {source: DirectionSource; workspace: string}) {
  const pages = source.page_start === source.page_end ? `p. ${source.page_start}` : `pp. ${source.page_start}–${source.page_end}`;
  return <article className="finding-card">
    <strong>{source.title}</strong><blockquote>{source.excerpt}</blockquote>
    <div className="finding-actions">
      <a href={sourceLink(source.document_id, source.page_start, source.chunk_id, workspace)}>Open source · {pages}</a>
      <SavePassage id={source.chunk_id} />
    </div>
  </article>;
}

export function ResearchDirectionStudio({workspaces, ask}: {
  workspaces: Workspace[]; ask: (question: FindingQuestion) => void;
}) {
  const [workspace, setWorkspace] = useState("");
  const [focus, setFocus] = useState("");
  const [focusDraft, setFocusDraft] = useState("");
  const [data, setData] = useState<ResearchDirections | null>(null);
  const [directionId, setDirectionId] = useState("");
  const [plans, setPlans] = useState<Record<string, InvestigationPlan>>({});
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setData(null);setDirectionId("");setError("");
    api.directions(workspace, focus, controller.signal).then(result => {
      if (!controller.signal.aborted) {
        setData(result);
        setDirectionId(result.directions[0]?.id ?? "");
      }
    }).catch(e => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to explore research directions.");
    });
    return () => controller.abort();
  }, [workspace, focus]);

  const selected = data?.directions.find(d => d.id === directionId);
  const key = JSON.stringify([workspace, focus, directionId]);
  const plan = selected && (plans[key] ?? selected.plan);
  return <div className="research-tools">
    <section className="panel atlas-toolbar dossier-controls">
      <label>Workspace<select value={workspace} onChange={e => setWorkspace(e.target.value)}>
        <option value="">Entire library</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select></label>
      <label>Research direction<select value={directionId} disabled={!data?.directions.length} onChange={e => setDirectionId(e.target.value)}>
        {!data?.directions.length && <option value="">No directions available</option>}
        {data?.directions.map(d => <option key={d.id} value={d.id}>{d.title} · {d.paper_count} {d.paper_count === 1 ? "paper" : "papers"}</option>)}
      </select></label>
    </section>
    <form className="panel direction-focus" onSubmit={e => {e.preventDefault(); setFocus(focusDraft.trim());}}>
      <label>Focus on a topic<input type="search" maxLength={180} value={focusDraft}
        onChange={e => setFocusDraft(e.target.value)} placeholder="Method, dataset, or benchmark" /></label>
      <button className="secondary" disabled={focusDraft.trim() === focus}>Apply topic</button>
      {(focus || focusDraft) && <button type="button" className="secondary" onClick={() => {setFocus(""); setFocusDraft("");}}>Clear</button>}
      {focus && <span className="tag">Topic · {focus}</span>}
    </form>
    {error && <p role="alert" className="notice error">{error}</p>}
    {!data && !error && <p role="status">Reviewing indexed limitations…</p>}
    {data && !selected && <section className="panel empty">No qualifying limitations matched in this scope’s reviewed passages.</section>}
    {selected && plan && <div className="research-controls direction-layout">
      <section className="panel">
        <h2>{selected.title}</h2>
        <p>{selected.reviewed_paper_count} {selected.reviewed_paper_count === 1 ? "paper" : "papers"} sampled for this theme. Verify the direction against the wider literature.</p>
        <div className="claim-group"><h3>Limitations and follow-ups · {selected.paper_count}</h3>
          {selected.evidence.map(source => <SourceCard source={source} workspace={workspace} key={source.chunk_id} />)}
        </div>
        <div className="claim-group"><h3>Reported coverage · {selected.coverage_paper_count}</h3>
          <p className="muted">Check whether these studies address the same methods and conditions as the limitation.</p>
          {selected.coverage.length ? selected.coverage.map(source => <SourceCard source={source} workspace={workspace} key={source.chunk_id} />)
            : <p>No explicit coverage was located in the sampled passages.</p>}
        </div>
      </section>
      <section className="panel plan-editor">
        <h2>Design an investigation</h2>
        <p>Adapt the draft to a particular method, dataset and evaluation protocol.</p>
        {fields.map(([field, label]) => <label key={field}>{label}
          <textarea rows={field === "validation" ? 4 : 2} maxLength={1500} value={plan[field]}
            onChange={e => {const value = e.target.value;setPlans(previous => ({...previous, [key]: {...plan, [field]: value}}));}} />
        </label>)}
        <div className="finding-actions">
          <button onClick={() => exportPlan(selected, plan)}>Export investigation plan</button>
          <button className="secondary" disabled={!plan.question.trim()} onClick={() => ask({
            workspaceId: workspace ? Number(workspace) : undefined,
            documentIds:[...new Set([...selected.evidence, ...selected.coverage].map(p => p.document_id))].slice(0, 12),
            question: `Which sources describe an uncovered limitation, and which report testing it? Compare the experimental conditions.\n\n${plan.question}`,
          })}>Ask Assistant</button>
        </div>
      </section>
    </div>}
    {!!data?.coverage_only.length && <section className="panel">
      <h2>Other themes with reported coverage</h2>
      {data.coverage_only.map(theme => <details className="claim-group" key={theme.id}>
        <summary>{theme.title} · {theme.paper_count} {theme.paper_count === 1 ? "paper" : "papers"}</summary>
        {theme.evidence.map(source => <SourceCard source={source} workspace={workspace} key={source.chunk_id} />)}
      </details>)}
    </section>}
  </div>;
}
