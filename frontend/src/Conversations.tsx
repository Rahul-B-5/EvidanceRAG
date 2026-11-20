import { useEffect, useRef, useState } from "react";
import { api, type Conversation, type Document, type Workspace } from "./api";
import { SavePassage } from "./SavedEvidence";
import type { FindingQuestion } from "./ComparisonStudio";
import type { AssistantPhase } from "./answerStream";
import { pageLabel } from "./pageLabel";
import { sourceLink } from "./sourceLink";

const MAX_PAPERS = 12;
const PHASE_LABELS: Record<AssistantPhase, string> = {
  retrieving:"Searching the selected scope…",
  generating:"Reading evidence and checking citations…",
  saving:"Saving the cited exchange…",
};

export function Conversations({documents, initial}: {documents: Document[]; initial?: FindingQuestion}) {
  const [list, setList] = useState<Array<{id: number; title: string}>>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState(initial?.workspaceId ? String(initial.workspaceId) : "");
  const [selected, setSelected] = useState<number[]>(initial?.documentIds ?? (initial?.documentId ? [initial.documentId] : []));
  const [choosePapers, setChoosePapers] = useState(selected.length > 0);
  const [paperFilter, setPaperFilter] = useState("");
  const [members, setMembers] = useState<{workspace: string; ids: Set<number>}>();
  const [scopeError, setScopeError] = useState("");
  const [query, setQuery] = useState(initial?.question ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [canCancel, setCanCancel] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const pendingRequest = useRef<string | null>(null);
  const needsSources = conversation?.scope_state === "legacy";
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {let cancelled = false;
    Promise.all([api.conversations(), api.workspaces()]).then(([c,w]) => {if (!cancelled) {setList(c.conversations);setWorkspaces(w.workspaces);}})
      .catch(e => {if (!cancelled) setError(String(e));});
    return () => {cancelled = true;};
  }, []);
  useEffect(() => {
    if (!workspace || !choosePapers || (conversation && !needsSources)) return;
    let cancelled = false;
    api.workspace(Number(workspace)).then(result => {
      if (!cancelled) setMembers({workspace, ids:new Set(result.documents.map(d => d.id))});
    }).catch(err => {if (!cancelled) setScopeError(err instanceof Error ? err.message : "Unable to load the workspace papers.");});
    return () => {cancelled = true;};
  }, [workspace, choosePapers, conversation, needsSources]);

  const scopeReady = !workspace || members?.workspace === workspace;
  const available = documents.filter(paper => !workspace || (scopeReady && members?.ids.has(paper.id)));
  const visible = available.filter(paper => `${paper.title} ${paper.filename}`.toLowerCase().includes(paperFilter.trim().toLowerCase()));
  const validSelection = selected.length > 0 && selected.every(id => available.some(paper => paper.id === id));
  const canSend = !!query.trim() && !busy && !needsSources &&
    (!!conversation || !choosePapers || (scopeReady && validSelection));
  const conversationSourceIds = conversation?.document_ids ?? (conversation?.document_id ? [conversation.document_id] : []);
  const scopeName = conversation?.workspace_id
    ? workspaces.find(item => item.id === conversation.workspace_id)?.name ?? `Workspace ${conversation.workspace_id}`
    : "Entire library";

  function togglePaper(id: number) {
    setSelected(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
  }

  async function open(id: string) {
    setStatus("");
    if (!id) {setConversation(null);setError("");return;}
    setBusy(true);setError("");
    try {
      const opened = await api.conversation(Number(id));
      if (opened.scope_state === "legacy") {
        setWorkspace("");setSelected([]);setMembers(undefined);setChoosePapers(true);
        setScopeError("");setPaperFilter("");
      }
      setConversation(opened);
    }
    catch(e) {setError(e instanceof Error ? e.message : "Unable to open conversation.");}
    finally {setBusy(false);}
  }
  async function restoreScope() {
    if (!conversation || !needsSources || !scopeReady || !validSelection || busy) return;
    setBusy(true);setError("");
    try {
      setConversation(await api.restoreConversationScope(
        conversation.id, selected, workspace ? Number(workspace) : undefined));
      setStatus("Sources saved for future replies.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save conversation sources.");
    } finally {
      setBusy(false);
    }
  }
  async function send() {
    if (!canSend || pending.current) return;
    const controller = new AbortController();
    const requestId = crypto.randomUUID();
    pendingRequest.current = requestId;
    pending.current = controller;
    const question = query.trim();
    let current = conversation;
    let finished = false;
    setBusy(true);setError("");
    setStatus("Opening the answer request…");
    try {
      current ??= await api.createConversation(
        question.slice(0,150), choosePapers ? selected : undefined, workspace ? Number(workspace) : undefined);
      setConversation(current);
      const {id, title} = current;
      if (!conversation) setList(previous => [{id,title}, ...previous]);
      controller.signal.throwIfAborted();
      setCanCancel(true);
      await api.reply(id, question, controller.signal, phase => {
        setStatus(PHASE_LABELS[phase]);
        if (phase === "saving") setCanCancel(false);
      }, requestId);
      finished = true;
      setQuery("");
      setConversation(await api.conversation(id));
      setStatus("");
    } catch(e) {
      if (controller.signal.aborted) {
        setStatus("Answer request cancelled.");
        if (current) {
          try {
            const latest = await api.conversation(current.id);
            setConversation(latest);
            if (latest.messages.slice(current.messages.length).some(m => m.role === "user" && m.content === question)) {
              setQuery("");
              setStatus("The answer had already been saved.");
            }
          } catch {
            setError("Unable to refresh the conversation. Reopen it to check for a completed answer.");
          }
        }
      } else {
        setStatus("");
        setError(finished ? "Answer saved. Reopen the conversation to view it."
          : e instanceof Error ? e.message : "Answer failed.");
      }
    } finally {
      pending.current = null;
      pendingRequest.current = null;
      setCanCancel(false);
      setBusy(false);
    }
  }
  return <div className="research-tools">
    <section className="panel research-controls assistant-history-bar"><label>Conversation<select disabled={busy} value={conversation?.id ?? ""} onChange={e => void open(e.target.value)}>
      <option value="">New conversation</option>{list.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
    </select></label><button className="secondary" disabled={busy} onClick={() => {setConversation(null);setQuery("");setError("");setStatus("");}}>New conversation</button></section>
    {(!conversation || needsSources) && <section className="panel assistant-scope" aria-label="Conversation source scope">
      {needsSources && <div>
        <h2>Restore conversation sources</h2>
        <p>The original scope could not be recovered. Choose papers to use for future replies.</p>
      </div>}
      <div className="research-controls">
        <label>Workspace<select disabled={busy} value={workspace} onChange={e => {
          setWorkspace(e.target.value); setSelected([]); setMembers(undefined); setScopeError(""); setPaperFilter("");
        }}><option value="">Entire library</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
        {!needsSources && <label>Sources<select disabled={busy} value={choosePapers ? "selected" : "all"} onChange={e => {
          setChoosePapers(e.target.value === "selected"); setScopeError("");
        }}><option value="all">All papers in scope</option><option value="selected">Select papers</option></select></label>}
      </div>
      {choosePapers && <fieldset className="assistant-papers" disabled={busy}>
        <legend>Source papers <small>{selected.length} of {MAX_PAPERS} selected</small></legend>
        {scopeError ? <p role="alert">{scopeError}</p> : !scopeReady ? <p role="status">Loading workspace papers…</p> : <>
          <label>Filter source papers<input type="search" value={paperFilter} onChange={e => setPaperFilter(e.target.value)} /></label>
          <div className="assistant-paper-list">
            {visible.map(paper => <label key={paper.id}>
              <input type="checkbox" checked={selected.includes(paper.id)}
                disabled={selected.length >= MAX_PAPERS && !selected.includes(paper.id)} onChange={() => togglePaper(paper.id)} />
              <span>{paper.title}</span>
            </label>)}
            {!visible.length && <p>No papers match this scope and filter.</p>}
          </div>
          {selected.length > 0 && !validSelection && <p role="alert">A selected source is outside the current scope. Clear the selection to continue.</p>}
          {!!selected.length && <button className="secondary" onClick={() => setSelected([])}>Clear selection</button>}
        </>}
      </fieldset>}
      {needsSources && <button disabled={busy || !scopeReady || !validSelection} onClick={() => void restoreScope()}>
        Save conversation sources
      </button>}
    </section>}
    {conversation && <section className="panel assistant-transcript"><h2>{conversation.title}</h2>
      <p className="assistant-scope-label">{needsSources ? "Source selection needed" : scopeName}{conversationSourceIds.length ? ` · ${conversationSourceIds.length} selected ${conversationSourceIds.length === 1 ? "paper" : "papers"}` : ""}</p>
      {!!conversationSourceIds.length && <ul className="assistant-source-tags" aria-label="Saved conversation sources">
        {conversationSourceIds.map(id => <li className="tag" key={id}>{documents.find(paper => paper.id === id)?.title ?? "Unavailable paper"}</li>)}
      </ul>}
      {conversation.messages.length === 0 && <p>No completed exchange yet.</p>}
      <div className="assistant-turns">{conversation.messages.map(m => <article className={`assistant-turn ${m.role === "user" ? "user" : "assistant"}`} key={m.id}><h3>{m.role === "user" ? "You" : "EvidenceRAG"}</h3><p>{m.content}</p>
        {m.citations.map(c => <div className="citation-row" key={c.evidence_id}>
          {documents.some(d => d.id === c.document_id)
            ? <><a href={sourceLink(c.document_id, c.page_start, c.chunk_id, conversation.workspace_id ?? undefined)}>[{c.evidence_id}] {c.title} · {pageLabel(c.page_start, c.page_end)}{c.section_title && ` · ${c.section_title}`}</a><SavePassage id={c.chunk_id} /></>
            : <span>[{c.evidence_id}] {c.title} · {pageLabel(c.page_start, c.page_end)} (source unavailable)</span>}
          {!!c.table_measurements?.length && <div className="citation-measurements">
            <span>Matched table cells</span>
            <dl>{c.table_measurements.map(cell => <div key={cell.column}><dt>{cell.column}</dt><dd>{cell.value}</dd></div>)}</dl>
          </div>}
        </div>)}
      </article>)}</div>
    </section>}
    {error && <p role="alert" className="notice error">{error}</p>}
    <form className="panel assistant-question" onSubmit={e => {e.preventDefault();void send();}}>
      <label>Question<textarea disabled={busy} maxLength={10000} value={query} onChange={e => setQuery(e.target.value)} /></label>
      <div className="finding-actions">
        <button disabled={!canSend}>Send question</button>
        {canCancel && <button type="button" className="secondary" onClick={async () => {
          setCanCancel(false);
          setStatus("Cancelling answer…");
          try {
            if (pendingRequest.current) await api.cancelAnswer(pendingRequest.current);
            pending.current?.abort();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Unable to cancel the answer.");
            setCanCancel(true);
          }
        }}>Cancel answer</button>}
      </div>
      {status && <p role="status" className="assistant-status">{status}</p>}
    </form>
  </div>;
}
