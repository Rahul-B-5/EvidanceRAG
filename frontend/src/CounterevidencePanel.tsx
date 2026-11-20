import { useEffect, useRef, useState } from "react";
import { api, type AtlasNode, type ClaimReview, type Counterevidence } from "./api";
import { SavePassage } from "./SavedEvidence";

const relations = {supports:"Supports", qualifies:"Qualifies", challenges:"Challenges", uncertain:"Uncertain"};
const alignments = {aligned:"Conditions align", different:"Conditions differ", unknown:"Alignment unclear"};

function ReviewEditor({prior, save}: {prior?: ClaimReview; save: (value: Pick<ClaimReview, "relation" | "alignment" | "note">) => Promise<void>}) {
  const [relation, setRelation] = useState<ClaimReview["relation"]>(prior?.relation ?? "uncertain");
  const [alignment, setAlignment] = useState<ClaimReview["alignment"]>(prior?.alignment ?? "unknown");
  const [note, setNote] = useState(prior?.note ?? "");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true); setStatus("");
    try {
      await save({relation, alignment, note});
      setStatus("Assessment saved.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Unable to save assessment.");
    } finally {
      setBusy(false);
    }
  }
  return <form className="claim-review" onSubmit={e => {e.preventDefault(); void submit();}}>
    <div className="finding-actions">
      <label>Relationship <select value={relation} onChange={e => setRelation(e.target.value as ClaimReview["relation"])}>
        {Object.entries(relations).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
      </select></label>
      <label>Experiment alignment <select value={alignment} onChange={e => setAlignment(e.target.value as ClaimReview["alignment"])}>
        {Object.entries(alignments).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
      </select></label>
    </div>
    <label>Assessment note<textarea value={note} maxLength={4000} rows={3} onChange={e => setNote(e.target.value)} /></label>
    <div className="finding-actions"><button disabled={busy}>{busy ? "Saving…" : "Save assessment"}</button><span role="status">{status}</span></div>
  </form>;
}

export function CounterevidencePanel({finding, workspace}: {finding: AtlasNode; workspace: string}) {
  const request = useRef<AbortController | null>(null);
  const [result, setResult] = useState<Counterevidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
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

  async function saveReview(chunk: number, value: Pick<ClaimReview, "relation" | "alignment" | "note">) {
    const review = await api.saveClaimReview(finding.id, chunk, workspace, value);
    setResult(current => current ? {
      ...current, reviews: [review, ...current.reviews.filter(r => r.candidate_chunk_id !== chunk)],
    } : current);
  }

  const reviews = new Map((result?.reviews ?? []).map(r => [r.candidate_chunk_id, r]));
  const candidates = new Map(result?.passages.map(p => [p.chunk_id, p]));
  for (const review of reviews.values()) {
    if (!candidates.has(review.candidate_chunk_id)) candidates.set(review.candidate_chunk_id, review.candidate_snapshot);
  }
  return <section className="counterevidence">
    <button className="secondary" disabled={busy} onClick={() => void search()}>{busy ? "Searching other papers…" : "Find counterevidence"}</button>
    {error && <p className="notice error" role="alert">{error}</p>}
    {result && <div>
      <h3>Candidate passages from other papers</h3>
      <p>Keyword overlap and qualifying language guide this search. Review both experiments before judging whether they disagree.</p>
      {!candidates.size && <p className="muted">No matching passages in the current scope.</p>}
      {Array.from(candidates.values(), p => <article className="finding-card" key={p.chunk_id}>
        <strong>{p.title}</strong>
        <blockquote>{p.excerpt}</blockquote>
        {p.opposing_statement && <p>Opposing statement under matching reported conditions.</p>}
        {p.signal && <p>Language to review: “{p.signal}”</p>}
        <p>{Object.keys(p.condition_labels).length
          ? `Overlapping reported labels: ${Object.entries(p.condition_labels).map(([key, value]) => `${key} · ${value}`).join(", ")}.`
          : "No shared condition labels found in this excerpt."}</p>
        {reviews.get(p.chunk_id) && <p>Your assessment · {relations[reviews.get(p.chunk_id)!.relation]} · {alignments[reviews.get(p.chunk_id)!.alignment]}</p>}
        <div className="finding-actions">
          <a href={`#paper=${p.document_id}&page=${p.page_start}`}>Open source · p. {p.page_start}</a>
          <SavePassage id={p.chunk_id} />
          <button className="secondary" aria-expanded={editing === p.chunk_id} onClick={() => setEditing(editing === p.chunk_id ? null : p.chunk_id)}>
            {editing === p.chunk_id ? "Close assessment" : reviews.has(p.chunk_id) ? "Edit assessment" : "Assess passage"}
          </button>
        </div>
        {editing === p.chunk_id && <ReviewEditor prior={reviews.get(p.chunk_id)} save={value => saveReview(p.chunk_id, value)} />}
      </article>)}
    </div>}
  </section>;
}
