import { useEffect, useState } from "react";
import { api, type ClaimDetail, type Document, type ResearchAssessment, type ResearchClaim, type Workspace } from "./api";
import { SavePassage } from "./SavedEvidence";
import { CounterevidencePanel } from "./CounterevidencePanel";
import type { FindingQuestion } from "./ComparisonStudio";
import "./claims.css";

export type ClaimLocation = {id?: string; workspace?: string; paper?: string};

const topics = {
  methodology:"Methods", datasets:"Datasets", training:"Training", metrics:"Metrics", results:"Results",
  limitations:"Limitations", architecture:"Architecture", protocol:"Evaluation protocol",
};
const assessments = {supported:"Supported", qualified:"Qualified", unsupported:"Unsupported", uncertain:"Uncertain"};
const size = 20;

function AssessmentEditor({claim, workspace, saved}: {
  claim: ClaimDetail; workspace: string; saved: (assessment: ResearchAssessment) => void;
}) {
  const [status, setStatus] = useState<ResearchAssessment["status"]>(claim.assessment?.status ?? "uncertain");
  const [note, setNote] = useState(claim.assessment?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function assess() {
    setBusy(true); setMessage(""); setError("");
    try {
      saved(await api.assessClaim(claim.id, workspace, {status, note, revision:claim.assessment?.revision ?? 0}));
      setMessage("Assessment saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save assessment.");
    } finally { setBusy(false); }
  }
  return <form className="plan-editor" onSubmit={event => {event.preventDefault(); void assess();}}>
    <h3>Researcher assessment</h3>
    <label>Evidence status<select value={status} onChange={e => setStatus(e.target.value as ResearchAssessment["status"])}>
      {Object.entries(assessments).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
    </select></label>
    <label>Assessment note<textarea rows={3} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></label>
    <button disabled={busy}>Save assessment</button>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </form>;
}

export function ClaimExplorer({initial, documents, workspaces, ask}: {
  initial?: ClaimLocation; documents: Document[]; workspaces: Workspace[]; ask: (value: FindingQuestion) => void;
}) {
  const [workspace, setWorkspace] = useState(initial?.workspace ?? "");
  const [paper, setPaper] = useState(initial?.paper ?? "");
  const [topic, setTopic] = useState("");
  const [status, setStatus] = useState("all");
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [id, setId] = useState(initial?.id ?? "");
  const [results, setResults] = useState<{claims: ResearchClaim[]; has_more: boolean}>();
  const [claim, setClaim] = useState<ClaimDetail>();
  const [listError, setListError] = useState("");
  const [claimError, setClaimError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [members, setMembers] = useState<number[]>();
  useEffect(() => {
    setMembers(undefined);
    if (!workspace) return;
    let active = true;
    api.workspace(Number(workspace)).then(result => {
      if (active) setMembers(result.documents.map(paper => paper.id));
    }).catch(() => { if (active) setMembers([]); });
    return () => {active = false;};
  }, [workspace]);

  useEffect(() => {
    const abort = new AbortController();
    const params = new URLSearchParams({query,topic,status,offset:String(page * size),limit:String(size)});
    if (workspace) params.set("workspace_id",workspace);
    if (paper) params.set("document_id",paper);
    setListError("");
    setResults(undefined);
    api.claims(params, abort.signal).then(value => {
      if (!abort.signal.aborted) setResults(value);
    }).catch(err => {if (!abort.signal.aborted) setListError(err.message);});
    return () => abort.abort();
  }, [workspace,paper,topic,status,query,page,refresh]);
  useEffect(() => {
    setClaim(undefined); setClaimError("");
    if (!id) return;
    const abort = new AbortController();
    api.claim(id, workspace, abort.signal).then(value => {
      if (!abort.signal.aborted) setClaim(value);
    }).catch(err => {if (!abort.signal.aborted) setClaimError(err.message);});
    return () => abort.abort();
  }, [id,workspace]);

  const source = claim?.finding.source;
  return <div className="research-tools">
    <form className="panel claim-filters" onSubmit={event => {event.preventDefault(); setPage(0); setQuery(draft.trim());}}>
      <label>Workspace<select value={workspace} onChange={e => {
        setWorkspace(e.target.value); setPaper(""); setId(""); setPage(0); setResults(undefined);
      }}><option value="">Library comparisons</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <label>Paper<select value={paper} onChange={e => {setPaper(e.target.value);setPage(0);}}>
        <option value="">All papers</option>{documents.filter(d => !workspace || members?.includes(d.id))
          .map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
      </select></label>
      <label>Topic<select value={topic} onChange={e => {setTopic(e.target.value);setPage(0);}}>
        <option value="">All topics</option>{Object.entries(topics).map(([id_, label]) => <option key={id_} value={id_}>{label}</option>)}
      </select></label>
      <label>Assessment<select value={status} onChange={e => {setStatus(e.target.value);setPage(0);}}>
        <option value="all">All assessments</option><option value="unreviewed">Unreviewed</option>
        {Object.entries(assessments).map(([id_, label]) => <option key={id_} value={id_}>{label}</option>)}
      </select></label>
      <label>Search claims<input type="search" maxLength={180} value={draft} onChange={e => setDraft(e.target.value)} /></label>
      <button>Search</button>
    </form>
    <div className="claim-layout">
      <section className="panel" aria-label="Claim search results">
        {listError && <p role="alert">{listError}</p>}
        {!results && !listError && <p role="status">Loading claims…</p>}
        {results?.claims.length === 0 && <p>No matching claims. Comparison Studio adds claims as it analyzes papers.</p>}
        <ul className="claim-list">{results?.claims.map(item => <li key={item.id}>
          <button className="secondary" aria-pressed={id === item.id} onClick={() => setId(item.id)}>
            <small>{item.title} · Page {item.finding.source.page_start}</small>
            <span>{item.quote}</span>
            <small>{item.assessment ? assessments[item.assessment.status] : "Unreviewed"}</small>
          </button>
        </li>)}</ul>
        {!!(page || results?.has_more) && <div className="finding-actions">
          <button className="secondary" disabled={page === 0} onClick={() => setPage(value => value - 1)}>Previous results</button>
          <button className="secondary" disabled={!results?.has_more || page * size >= 10000} onClick={() => setPage(value => value + 1)}>Next results</button>
        </div>}
      </section>
      <section className="panel claim-detail" aria-label="Claim details">
        {claimError && <p role="alert">{claimError}</p>}
        {!id && <p>Select a claim to inspect its source and record an assessment.</p>}
        {!!id && !claim && !claimError && <p role="status">Loading claim…</p>}
        {claim && source && <>
          <h2>{claim.title}</h2>
          <p>{claim.finding.outcome.metric || claim.finding.relative_statement ? "Reported result" : "Author excerpt"} · Indexed source located</p>
          <blockquote>{claim.quote}</blockquote>
          <div className="finding-actions">
            <a href={`#paper=${source.document_id}&page=${source.page_start}${workspace ? `&workspace=${workspace}` : ""}`}>Open source · p. {source.page_start}{source.page_end !== source.page_start ? `–${source.page_end}` : ""}</a>
            <SavePassage key={source.chunk_id} id={source.chunk_id} />
            <a href={`#atlas=${id}${workspace ? `&workspace=${workspace}` : ""}`}>Explore in Atlas</a>
            <button className="secondary" onClick={() => ask({documentId:claim.document_id,workspaceId:workspace ? Number(workspace) : undefined,
              question:`What evidence and qualifications does this paper provide for this excerpt?\n\n${claim.quote}`})}>Ask Assistant</button>
          </div>
          <p className="muted">Passage {claim.chunk_id} · Comparison run {claim.run_id.slice(0,8)}</p>
          {(claim.finding.method || Object.keys(claim.finding.outcome).length > 0) && <dl className="claim-labels">
            {Object.entries({...claim.finding.outcome, ...(claim.finding.method ? {method:claim.finding.method} : {})})
              .map(([key,value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
          </dl>}
          <AssessmentEditor key={`assessment:${claim.id}`} claim={claim} workspace={workspace} saved={assessment => {
            setClaim({...claim,assessment}); setRefresh(value => value + 1);
          }} />
          <h3>Related claims</h3>
          {claim.related.length === 0 && <p className="muted">No cross-paper claims with matching study labels.</p>}
          <ul className="claim-list">{claim.related.map(item => <li key={item.id}>
            <button className="secondary" onClick={() => setId(item.id)}><small>{item.title} · Page {item.finding.source.page_start}</small>
              <span>{item.quote}</span><small>{Object.entries(item.shared_labels).map(([key,value]) => `${key} · ${value}`).join(", ")}</small></button>
          </li>)}</ul>
          <CounterevidencePanel key={`counterevidence:${claim.id}`} workspace={workspace}
            finding={{id:claim.id,kind:"finding",label:claim.quote,provenance:source}} />
        </>}
      </section>
    </div>
  </div>;
}
