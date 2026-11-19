import { useEffect, useState } from "react";
import { api, type Conversation, type Document, type Workspace } from "./api";

export function Conversations({documents}: {documents: Document[]}) {
  const [list, setList] = useState<Array<{id: number; title: string}>>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {let cancelled = false;
    Promise.all([api.conversations(), api.workspaces()]).then(([c,w]) => {if (!cancelled) {setList(c.conversations);setWorkspaces(w.workspaces);}})
      .catch(e => {if (!cancelled) setError(String(e));});
    return () => {cancelled = true;};
  }, []);
  async function open(id: string) {
    if (!id) {setConversation(null);setError("");return;}
    setBusy(true);setError("");
    try {setConversation(await api.conversation(Number(id)));}
    catch(e) {setError(e instanceof Error ? e.message : "Unable to open conversation.");}
    finally {setBusy(false);}
  }
  async function send() {
    if (!query.trim() || busy) return;
    setBusy(true);setError("");
    try {
      const current = conversation ?? await api.createConversation(query.trim().slice(0,150), source ? Number(source) : undefined, workspace ? Number(workspace) : undefined);
      setConversation({...current, messages:current.messages ?? []});
      setList((await api.conversations()).conversations);
      await api.reply(current.id, query.trim());
      setConversation(await api.conversation(current.id));setQuery("");
    } catch(e) {setError(e instanceof Error ? e.message : "Answer failed.");}
    finally {setBusy(false);}
  }
  return <div className="research-tools">
    <section className="panel research-controls"><label>Conversation<select disabled={busy} value={conversation?.id ?? ""} onChange={e => void open(e.target.value)}>
      <option value="">New conversation</option>{list.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
    </select></label><button disabled={busy} onClick={() => {setConversation(null);setQuery("");setError("");}}>New conversation</button></section>
    {!conversation && <section className="panel research-controls"><label>Workspace<select disabled={busy} value={workspace} onChange={e => {setWorkspace(e.target.value);setSource("");}}>
      <option value="">Entire library</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
    </select></label><label>Paper<select disabled={busy || !!workspace} value={source} onChange={e => setSource(e.target.value)}><option value="">All papers in scope</option>{documents.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}</select></label></section>}
    {conversation && <section className="panel"><h2>{conversation.title}</h2><p>Scope: {conversation.workspace_id ? `Workspace ${conversation.workspace_id}` : conversation.document_id ? documents.find(d => d.id === conversation.document_id)?.title ?? "Deleted paper" : "Entire library"}</p>
      {conversation.messages.length === 0 && <p>No completed exchange yet.</p>}
      {conversation.messages.map(m => <article className="research-passages" key={m.id}><h3>{m.role === "user" ? "You" : "EvidenceRAG"}</h3><p style={{whiteSpace:"pre-wrap"}}>{m.content}</p>
        {m.citations.map(c => <p key={c.evidence_id}>{documents.find(d => d.id === c.document_id)?.has_stored_source ? <a target="_blank" rel="noreferrer" href={`${api.sourceUrl(c.document_id)}#page=${c.page_start}`}>[{c.evidence_id}] {c.title} · page {c.page_start}</a> : <span>[{c.evidence_id}] {c.title} · page {c.page_start} (source unavailable)</span>}</p>)}
      </article>)}
    </section>}
    {error && <p role="alert" className="notice error">{error} Your question remains below for retry.</p>}
    <form className="panel" onSubmit={e => {e.preventDefault();void send();}}><label>Question<textarea style={{display:"block",width:"100%",margin:"1rem 0"}} disabled={busy} maxLength={10000} value={query} onChange={e => setQuery(e.target.value)} /></label><button disabled={busy || !query.trim()}>{busy ? "Preparing answer…" : "Send question"}</button><p>Answers require a configured provider. Evidence explorer works without one.</p></form>
  </div>;
}
