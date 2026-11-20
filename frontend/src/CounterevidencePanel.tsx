import { useEffect, useRef, useState } from "react";
import { api, type AtlasNode, type Counterevidence } from "./api";
import { SavePassage } from "./SavedEvidence";

export function CounterevidencePanel({finding, workspace}: {finding: AtlasNode; workspace: string}) {
  const request = useRef<AbortController | null>(null);
  const [result, setResult] = useState<Counterevidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => () => request.current?.abort(), []);

  async function search() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      const data = await api.counterevidence(finding.id, workspace, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to find related evidence.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <section className="counterevidence">
    <button className="secondary" disabled={busy} onClick={() => void search()}>{busy ? "Searching other papers…" : "Find counterevidence"}</button>
    {error && <p className="notice error" role="alert">{error}</p>}
    {result && <div>
      <h3>Candidate passages from other papers</h3>
      <p>Keyword overlap and qualifying language guide this search. Review both experiments before judging whether they disagree.</p>
      {!result.passages.length && <p className="muted">No matching passages in the current scope.</p>}
      {result.passages.map(p => <article className="finding-card" key={p.chunk_id}>
        <strong>{p.title}</strong>
        <blockquote>{p.excerpt}</blockquote>
        {p.signal && <p>Language to review: “{p.signal}”</p>}
        <p>{Object.keys(p.condition_labels).length
          ? `Overlapping reported labels: ${Object.entries(p.condition_labels).map(([key, value]) => `${key} · ${value}`).join(", ")}.`
          : "No shared condition labels found in this excerpt."}</p>
        <div className="finding-actions"><a href={`#paper=${p.document_id}&page=${p.page_start}`}>Open source · p. {p.page_start}</a><SavePassage id={p.chunk_id} /></div>
      </article>)}
    </div>}
  </section>;
}
