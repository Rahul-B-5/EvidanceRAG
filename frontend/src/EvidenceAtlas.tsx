import { useEffect, useRef, useState } from "react";
import { api, type Atlas, type AtlasNode, type Workspace } from "./api";
import type { FindingQuestion } from "./ComparisonStudio";
import { SavePassage } from "./SavedEvidence";
import { CounterevidencePanel } from "./CounterevidencePanel";
import { OpposingFindings } from "./OpposingFindings";
import type { ClaimLocation } from "./ClaimExplorer";
import "./atlas.css";

const typeNames: Record<string, string> = {
  paper: "Paper", finding: "Excerpt", passage: "Passage", topic: "Topic",
  dataset: "Dataset", metric: "Metric", baseline: "Baseline",
};

function clampLabel(s: string) {
  return s.length > 64 ? s.slice(0, 61) + "…" : s;
}

export function EvidenceAtlas({compare, ask, initial}: {compare: () => void; ask: (q: FindingQuestion) => void; initial?: ClaimLocation}) {
  const [workspace, setWorkspace] = useState(initial?.workspace ?? "");
  const [target, setTarget] = useState(initial?.id);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [atlas, setAtlas] = useState<Atlas | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [relation, setRelation] = useState("");
  const [selected, setSelected] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [zoom, setZoom] = useState(1);
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<{x: number; y: number; left: number; top: number} | null>(null);

  useEffect(() => {
    let alive = true;
    api.workspaces().then(r => {if (alive) setWorkspaces(r.workspaces);})
      .catch(() => {if (alive) setError("Unable to load workspace options.");});
    return () => {alive = false;};
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setAtlas(null); setSelected(""); setError(""); setRelation("");
    api.atlas(workspace, controller.signal, target).then(data => {
      if (!controller.signal.aborted) {
        setAtlas(data);
        setSelected(data.nodes.find(n => n.id === target)?.id ?? data.nodes.find(n => n.kind === "finding")?.id ?? data.nodes[0]?.id ?? "");
      }
    }).catch(e => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to load evidence graph.");
    });
    return () => controller.abort();
  }, [workspace,target]);

  const nodes = new Map(atlas?.nodes.map(n => [n.id, n]));
  const center = nodes.get(selected);
  const links = atlas?.edges.filter(edge => (!relation || edge.relation === relation)
    && (edge.source === selected || edge.target === selected)) ?? [];
  const neighbors = links.flatMap(edge => {
    const node = nodes.get(edge.source === selected ? edge.target : edge.source);
    return node && (!kind || node.kind === kind) ? [{node, edge}] : [];
  });
  const visible = neighbors.slice(0, showAll ? 24 : 8);
  const matching = atlas?.nodes.filter(n => (!kind || n.kind === kind)
    && n.label.toLowerCase().includes(search.trim().toLowerCase())) ?? [];
  const available = new Set(atlas?.nodes.map(n => n.kind));
  const relations = new Set(atlas?.edges.map(e => e.relation));

  function focus(node: AtlasNode) {
    setSelected(node.id);
    setShowAll(false);
  }

  const board = showAll ? 920 : 680;
  const radius = showAll ? 340 : 225;
  const source = center?.provenance;
  return <div className="research-tools">
    <section className="panel atlas-toolbar">
      <label>Workspace<select value={workspace} onChange={e => {setWorkspace(e.target.value);setTarget(undefined);}}>
        <option value="">Library comparisons</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select></label>
      <label>Find a node<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Paper, metric or excerpt" /></label>
      <label>Node type<select value={kind} onChange={e => setKind(e.target.value)}><option value="">All types</option>
        {Array.from(available, k => <option key={k} value={k}>{typeNames[k]}</option>)}</select></label>
      <label>Relationship<select value={relation} onChange={e => setRelation(e.target.value)}><option value="">All relationships</option>
        {Array.from(relations, r => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}</select></label>
    </section>
    {error && <p role="alert" className="notice error">{error}</p>}
    {!atlas && !error && <p role="status">Loading evidence graph…</p>}
    {atlas?.edges.length === 0 && <section className="panel empty">
      <p>This scope has no comparison findings yet. Compare papers to populate the atlas.</p>
      <button onClick={compare}>Open Comparison Studio</button>
    </section>}
    {!!atlas?.edges.length && <>
      <OpposingFindings pairs={atlas.contradictions ?? []} ask={ask} workspaceId={workspace ? Number(workspace) : undefined}
        focus={id => {
          const node = nodes.get(id);
          if (!node) return;
          setRelation("potential_disagreement");
          setKind("");
          focus(node);
          stage.current?.focus();
        }} />
      <div className="atlas-layout">
      <section className="panel atlas-index" aria-label="Graph node search results">
        <h2>Nodes</h2><p>{matching.length} matches</p>
        <ul>{matching.slice(0, 40).map(n => <li key={n.id}>
          <button className="secondary" aria-pressed={n.id === selected} onClick={() => focus(n)}><small>{typeNames[n.kind]}</small>{clampLabel(n.label)}</button>
        </li>)}</ul>
        {matching.length > 40 && <p>Refine the search to see more matches.</p>}
      </section>
      <div className="research-tools">
        <section className="panel atlas-graph">
          <div className="comparison-heading">
            <h2>Evidence neighborhood</h2>
            <label>Zoom <input aria-label="Graph zoom" type="range" min={0.6} max={1.5} step={0.1} value={zoom} onChange={e => setZoom(Number(e.target.value))} /></label>
          </div>
          <div ref={stage} className="atlas-stage" tabIndex={0} aria-label="Scrollable evidence graph"
            onPointerDown={event => {
              if (!(event.target instanceof HTMLElement) || event.target.closest("button")) return;
              drag.current = {x: event.clientX, y: event.clientY, left: event.currentTarget.scrollLeft, top: event.currentTarget.scrollTop};
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={event => {
              if (!drag.current || !stage.current) return;
              stage.current.scrollLeft = drag.current.left + drag.current.x - event.clientX;
              stage.current.scrollTop = drag.current.top + drag.current.y - event.clientY;
            }}
            onPointerUp={() => {drag.current = null;}} onPointerCancel={() => {drag.current = null;}}>
            <div className="atlas-plane" style={{width: board * zoom, height: board * zoom}}>
              <div className="atlas-centered" style={{top: board * zoom / 2, left: board * zoom / 2}}>
                {visible.map(({node, edge}, index) => {
                  const angle = index * Math.PI * 2 / visible.length - Math.PI / 2;
                  const offset = radius * zoom;
                  return <div key={`${node.id}-${edge.relation}`}>
                    <span aria-hidden="true" className="atlas-edge" style={{width: offset, transform: `rotate(${angle}rad)`}} />
                    <button className="secondary atlas-node" data-kind={node.kind}
                      style={{left: Math.cos(angle) * offset, top: Math.sin(angle) * offset}}
                      title={node.label} onClick={() => focus(node)}><small>{typeNames[node.kind]}</small>{clampLabel(node.label)}</button>
                  </div>;
                })}
                {center && <div className="atlas-node atlas-focus" data-kind={center.kind}><small>{typeNames[center.kind]}</small>{clampLabel(center.label)}</div>}
              </div>
            </div>
          </div>
          <div className="comparison-heading">
            <p>{visible.length} of {neighbors.length} matching relationships</p>
            {neighbors.length > 8 && <button className="secondary" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>{showAll ? "Collapse neighborhood" : "Expand neighborhood"}</button>}
          </div>
        </section>
        {center && <section className="panel atlas-detail">
          <h2>{typeNames[center.kind]}</h2><p>{center.label}</p>
          {source && <div className="finding-actions">
            <a href={`#paper=${source.document_id}&page=${source.page_start}`}>Open source · p. {source.page_start}</a><SavePassage id={source.chunk_id} />
            {center.kind === "finding" && <a href={`#claim=${center.id}${workspace ? `&workspace=${workspace}` : ""}`}>Open claim</a>}
            {center.kind === "finding" && <button className="secondary" onClick={() => ask({
              documentId: source.document_id, workspaceId: workspace ? Number(workspace) : undefined,
              question: `What context or qualifications does this paper provide for this excerpt?\n\n“${center.label}”`,
            })}>Ask Assistant</button>}
          </div>}
          <h3>Relationship provenance</h3>
          <ul>{visible.map(({node, edge}) => <li key={`${node.id}-${edge.relation}`}>
            <button className="secondary" onClick={() => focus(node)}>{clampLabel(node.label)}</button>
            <span>{edge.relation.replaceAll("_", " ")}</span>
            <a href={`#paper=${edge.provenance.document_id}&page=${edge.provenance.page_start}`}>Passage {edge.provenance.chunk_id} · p. {edge.provenance.page_start}</a>
            {edge.related_provenance && <a href={`#paper=${edge.related_provenance.document_id}&page=${edge.related_provenance.page_start}`}>
              Passage {edge.related_provenance.chunk_id} · p. {edge.related_provenance.page_start}
            </a>}
          </li>)}</ul>
          <p>Relationships describe the selected indexed text and its extracted labels. Assess scientific support in the original source.</p>
          {center.kind === "finding" && <CounterevidencePanel key={center.id} finding={center} workspace={workspace} />}
        </section>}
      </div>
    </div></>}
  </div>;
}
