import { useEffect, useState } from "react";
import { api, type InvestigationPlan, type ResearchDirections, type Workspace } from "./api";
import type { FindingQuestion } from "./ComparisonStudio";
import { SavePassage } from "./SavedEvidence";

const fields: Array<[keyof InvestigationPlan, string]> = [
  ["question", "Research question"],
  ["hypothesis", "Testable hypothesis"],
  ["baseline", "Baselines and controls"],
  ["metrics", "Primary metrics"],
  ["validation", "Validation steps"],
];

function exportPlan(direction: ResearchDirections["directions"][number], plan: InvestigationPlan) {
  const plain = (s: string) => s.replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c] ?? c));
  const sections = [
    "# Research investigation plan",
    `## ${direction.title}`,
    "Candidate direction based on the reviewed local scope. Verify novelty in a wider literature search.",
    ...fields.flatMap(([key, label]) => [`### ${label}`, plain(plan[key].trim() || "To be specified.")]),
    "## Indexed source excerpts",
    ...direction.evidence.flatMap(p => [
      `### ${plain(p.title.replace(/\s+/g, " "))}`,
      `> ${plain(p.excerpt)}`,
      `Paper ${p.document_id} · pages ${p.page_start}–${p.page_end} · passage ${p.chunk_id}`,
    ]),
  ];
  const url = URL.createObjectURL(new Blob([sections.join("\n\n") + "\n"], {type: "text/markdown;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url; link.download = `evidencerag-plan-${direction.id}.md`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ResearchDirectionStudio({workspaces, ask}: {
  workspaces: Workspace[]; ask: (question: FindingQuestion) => void;
}) {
  const [workspace, setWorkspace] = useState("");
  const [data, setData] = useState<ResearchDirections | null>(null);
  const [directionId, setDirectionId] = useState("");
  const [plans, setPlans] = useState<Record<string, InvestigationPlan>>({});
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setData(null);setDirectionId("");setError("");
    api.directions(workspace, controller.signal).then(result => {
      if (!controller.signal.aborted) {
        setData(result);
        setDirectionId(result.directions[0]?.id ?? "");
      }
    }).catch(e => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to explore research directions.");
    });
    return () => controller.abort();
  }, [workspace]);

  const selected = data?.directions.find(d => d.id === directionId);
  const key = `${workspace}:${directionId}`;
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
    {error && <p role="alert" className="notice error">{error}</p>}
    {!data && !error && <p role="status">Reviewing indexed limitations…</p>}
    {data && !selected && <section className="panel empty">No qualifying limitations matched in this scope’s reviewed passages.</section>}
    {selected && plan && <div className="research-controls">
      <section className="panel">
        <h2>{selected.title}</h2>
        <p>Matching language in {selected.paper_count} {selected.paper_count === 1 ? "paper" : "papers"} from {data?.reviewed_paper_count} papers reviewed.</p>
        <p className="muted">Possible direction · Requires broader literature verification</p>
        {selected.evidence.map(p => <article className="finding-card" key={p.chunk_id}>
          <strong>{p.title}</strong><blockquote>{p.excerpt}</blockquote>
          <div className="finding-actions"><a href={`#paper=${p.document_id}&page=${p.page_start}`}>Open source · p. {p.page_start}</a><SavePassage id={p.chunk_id} /></div>
        </article>)}
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
            question: `What evidence in this scope informs this proposed investigation?\n\n${plan.question}`,
          })}>Ask Assistant</button>
        </div>
      </section>
    </div>}
  </div>;
}
