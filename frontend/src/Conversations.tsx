import { useEffect, useState } from "react";
import { api, type Conversation, type Document, type Workspace } from "./api";
import { SavePassage } from "./SavedEvidence";
import type { FindingQuestion } from "./ComparisonStudio";

const MAX_PAPERS = 12;

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
  useEffect(() => {let cancelled = false;
    Promise.all([api.conversations(), api.workspaces()]).then(([c,w]) => {if (!cancelled) {setList(c.conversations);setWorkspaces(w.workspaces);}})
      .catch(e => {if (!cancelled) setError(String(e));});
    return () => {cancelled = true;};
  }, []);
  useEffect(() => {
    if (!workspace || !choosePapers || conversation) return;
    let cancelled = false;
    api.workspace(Number(workspace)).then(result => {
      if (!cancelled) setMembers({workspace, ids:new Set(result.documents.map(d => d.id))});
    }).catch(err => {if (!cancelled) setScopeError(err instanceof Error ? err.message : "Unable to load the workspace papers.");});
    return () => {cancelled = true;};
  }, [workspace, choosePapers, conversation]);

  const scopeReady = !workspace || members?.workspace === workspace;
  const available = documents.filter(paper => !workspace || (scopeReady && members?.ids.has(paper.id)));
  const visible = available.filter(paper => `${paper.title} ${paper.filename}`.toLowerCase().includes(paperFilter.trim().toLowerCase()));
  const validSelection = selected.length > 0 && selected.every(id => available.some(paper => paper.id === id));
  const canSend = !!query.trim() && !busy && (!!conversation || !choosePapers || (scopeReady && validSelection));
  const conversationSourceIds = conversation?.document_ids ?? (conversation?.document_id ? [conversation.document_id] : []);
  const scopeName = conversation?.workspace_id
    ? workspaces.find(item => item.id === conversation.workspace_id)?.name ?? `Workspace ${conversation.workspace_id}`
    : "Entire library";

  function togglePaper(id: number) {
    setSelected(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
  }

  async function open(id: string) {
    if (!id) {setConversation(null);setError("");return;}
    setBusy(true);setError("");
    try {setConversation(await api.conversation(Number(id)));}
    catch(e) {setError(e instanceof Error ? e.message : "Unable to open conversation.");}
    finally {setBusy(false);}
  }
  async function send() {
    if (!canSend) return;
    setBusy(true);setError("");
    try {
      const current = conversation ?? await api.createConversation(
        query.trim().slice(0,150), choosePapers ? selected : undefined, workspace ? Number(workspace) : undefined);
      setConversation(current);
      if (!conversation) setList(previous => [{id:current.id,title:current.title}, ...previous]);
      await api.reply(current.id, query.trim());
      setConversation(await api.conversation(current.id));setQuery("");
    } catch(e) {setError(e instanceof Error ? e.message : "Answer failed.");}
    finally {setBusy(false);}
  }
  return <div className="research-tools">
    <section className="panel research-controls"><label>Conversation<select disabled={busy} value={conversation?.id ?? ""} onChange={e => void open(e.target.value)}>
      <option value="">New conversation</option>{list.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
    </select></label><button disabled={busy} onClick={() => {setConversation(null);setQuery("");setError("");}}>New conversation</button></section>
    {!conversation && <section className="panel assistant-scope" aria-label="Conversation source scope">
      <div className="research-controls">
        <label>Workspace<select disabled={busy} value={workspace} onChange={e => {
          setWorkspace(e.target.value); setSelected([]); setMembers(undefined); setScopeError(""); setPaperFilter("");
        }}><option value="">Entire library</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
        <label>Sources<select disabled={busy} value={choosePapers ? "selected" : "all"} onChange={e => {
          setChoosePapers(e.target.value === "selected"); setScopeError("");
        }}><option value="all">All papers in scope</option><option value="selected">Select papers</option></select></label>
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
    </section>}
    {conversation && <section className="panel"><h2>{conversation.title}</h2>
      <p className="assistant-scope-label">{scopeName}{conversationSourceIds.length ? ` · ${conversationSourceIds.length} selected ${conversationSourceIds.length === 1 ? "paper" : "papers"}` : ""}</p>
      {!!conversationSourceIds.length && <ul className="assistant-source-tags" aria-label="Saved conversation sources">
        {conversationSourceIds.map(id => <li className="tag" key={id}>{documents.find(paper => paper.id === id)?.title ?? "Unavailable paper"}</li>)}
      </ul>}
      {conversation.messages.length === 0 && <p>No completed exchange yet.</p>}
      {conversation.messages.map(m => <article className="research-passages" key={m.id}><h3>{m.role === "user" ? "You" : "EvidenceRAG"}</h3><p style={{whiteSpace:"pre-wrap"}}>{m.content}</p>
        {m.citations.map(c => <div className="citation-row" key={c.evidence_id}>
          {documents.some(d => d.id === c.document_id)
            ? <><a href={`#paper=${c.document_id}&page=${c.page_start}`}>[{c.evidence_id}] {c.title} · page {c.page_start}</a><SavePassage id={c.chunk_id} /></>
            : <span>[{c.evidence_id}] {c.title} · page {c.page_start} (source unavailable)</span>}
        </div>)}
      </article>)}
    </section>}
    {error && <p role="alert" className="notice error">{error} Your question remains below for retry.</p>}
    <form className="panel assistant-question" onSubmit={e => {e.preventDefault();void send();}}>
      <label>Question<textarea disabled={busy} maxLength={10000} value={query} onChange={e => setQuery(e.target.value)} /></label>
      <button disabled={!canSend}>{busy ? "Preparing answer…" : "Send question"}</button>
    </form>
  </div>;
}
