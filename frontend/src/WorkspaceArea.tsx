import { useEffect, useState } from "react";
import { api, type Document, type Workspace } from "./api";
import { ResearchTools } from "./ResearchTools";
import { ComparisonStudio, type FindingQuestion } from "./ComparisonStudio";

export function WorkspaceArea({documents, manage = false, compare}: {
  documents: Document[]; manage?: boolean; compare?: (question: FindingQuestion) => void;
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selected, setSelected] = useState("");
  const [members, setMembers] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setMembers([]);
    Promise.all([api.workspaces(), selected ? api.workspace(Number(selected)) : Promise.resolve(null)])
      .then(([list, detail]) => {if (!cancelled) {setWorkspaces(list.workspaces); setMembers(detail?.documents.map(d => d.id) ?? []);}})
      .catch(e => {if (!cancelled) setError(e instanceof Error ? e.message : "Unable to load workspace.");})
      .finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [selected, revision]);
  async function membership(id: number, add: boolean) {
    setSaving(true); setError("");
    try {await api.membership(Number(selected), id, add); setRevision(n => n + 1);}
    catch(e) {setError(e instanceof Error ? e.message : "Membership update failed.");}
    finally {setSaving(false);}
  }
  async function create() {
    if (!name.trim()) return;
    setSaving(true); setError("");
    try {const w = await api.createWorkspace(name.trim(), ""); setSelected(String(w.id)); setName("");}
    catch(e) {setError(e instanceof Error ? e.message : "Workspace creation failed.");}
    finally {setSaving(false);}
  }
  const scoped = selected ? documents.filter(d => members.includes(d.id)) : documents;
  const workspaceId = selected ? Number(selected) : undefined;
  return <div className="research-tools">
    <section className="panel research-controls">
      <label>Workspace<select value={selected} disabled={saving} onChange={e => {setSelected(e.target.value); setLoading(true);}}>
        <option value="">Entire library</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select></label>
      {manage && <form onSubmit={e => {e.preventDefault(); void create();}}>
        <label>New workspace name<input maxLength={160} value={name} onChange={e => setName(e.target.value)} /></label>
        <button disabled={saving || !name.trim()}>Create workspace</button>
      </form>}
    </section>
    {error && <p role="alert" className="notice error">{error}</p>}
    {loading ? <p role="status">Loading workspace…</p> : !error && <>
      {manage && <section className="panel"><h2>Workspace papers</h2>
        <p>{selected ? "Change membership here. Removing membership keeps the paper in your library." : "Select a workspace to organize its papers."}</p>
        {selected && <fieldset disabled={saving}>{documents.map(d => <label style={{display:"block",padding:".6rem"}} key={d.id}>
          <input type="checkbox" checked={members.includes(d.id)} onChange={e => void membership(d.id, e.target.checked)} /> {d.title}
        </label>)}</fieldset>}
      </section>}
      {compare
        ? <ComparisonStudio key={selected} documents={scoped} workspaceId={workspaceId} ask={compare} />
        : <ResearchTools key={`${selected}-${revision}`} workspaceId={workspaceId} documents={scoped} />}
    </>}
  </div>;
}
