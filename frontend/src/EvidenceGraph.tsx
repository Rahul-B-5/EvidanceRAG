import { useState } from "react";
import type { StructuredComparison } from "./api";

type GraphProps = {
  papers: StructuredComparison["papers"];
  topics: string[];
  labels: Record<string, string>;
  inspect: (topic: string, paper: number) => void;
};

export function EvidenceGraph({papers, topics, labels, inspect}: GraphProps) {
  const [selected, setSelected] = useState(papers[0]?.document_id);
  const [activeTopic, setActiveTopic] = useState("");
  const paper = papers.find(p => p.document_id === selected) ?? papers[0];
  if (!paper) return null;
  const connected = topics.filter(t => paper.findings.some(f => f.topic === t));
  const topic = connected.includes(activeTopic) ? activeTopic : connected[0];
  const sources = new Map(paper.findings.filter(f => f.topic === topic)
    .map(f => [f.source.chunk_id, f.source]));

  return <section className="evidence-graph" aria-label="Evidence graph">
    <div><h3>Papers</h3>{papers.map(p => <button className="secondary" key={p.document_id}
      aria-pressed={p.document_id === paper.document_id} onClick={() => {setSelected(p.document_id);setActiveTopic("");}}>{p.title}</button>)}</div>
    <div><h3>Connected topics</h3>{connected.map(t => <button className="secondary" key={t}
      aria-pressed={topic === t} onClick={() => setActiveTopic(t)}>{labels[t]} <small>{paper.findings.filter(f => f.topic === t).length}</small></button>)}
      {!connected.length && <p className="muted">No verified findings for this paper and filter.</p>}</div>
    <div><h3>Source passages</h3>{Array.from(sources.values(), s => <a key={s.chunk_id}
      href={`#paper=${s.document_id}&page=${s.page_start}`}>Page {s.page_start}{s.page_end !== s.page_start ? `–${s.page_end}` : ""} · Passage {s.chunk_id}</a>)}
      {!!topic && <button className="secondary" onClick={() => inspect(topic, paper.document_id)}>Inspect connected claims</button>}</div>
  </section>;
}
