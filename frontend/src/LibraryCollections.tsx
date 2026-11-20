import { useEffect, useState } from "react";
import { api, type Collection, type Document, type Workspace } from "./api";

export function LibraryCollections({documents, workspaces, filter, visible}: {
  documents: Document[]; workspaces: Workspace[]; filter: (ids: number[] | null) => void; visible: boolean;
}) {
  const [workspace, setWorkspace] = useState("");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [scoped, setScoped] = useState<number[] | null>(null);
  const [selected, setSelected] = useState("");
  const [members, setMembers] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [renamed, setRenamed] = useState("");
  const [manageable, setManageable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!visible) return;
    let active = true;
    setLoading(true);setError("");
    Promise.all([
      api.collections(workspace),
      workspace ? api.workspace(Number(workspace)) : Promise.resolve(null),
      selected ? api.collection(selected) : Promise.resolve(null),
    ]).then(([list, group, collection]) => {
      if (!active) return;
      const workspaceIds = group?.documents.map(p => p.id) ?? null;
      const collectionIds = collection?.document_ids ?? [];
      setScoped(workspaceIds);setMembers(collectionIds);setCollections(list.collections);
      setRenamed(collection?.name ?? "");
      filter(collection ? collectionIds : workspaceIds);
    }).catch(e => {
      if (active) setError(e instanceof Error ? e.message : "Unable to load collections.");
    }).finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [workspace, selected, revision, filter, visible]);

  async function mutate(action: () => Promise<unknown>) {
    setBusy(true);setError("");
    try {
      await action();
      setRevision(n => n + 1);
    } catch(e) {
      setError(e instanceof Error ? e.message : "Collection update failed.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="library-collections" aria-label="Library collections">
    <div className="atlas-toolbar dossier-controls">
      <label>Workspace <select disabled={busy} value={workspace} onChange={e => {
        setWorkspace(e.target.value);setCollections([]);setSelected("");setScoped([]);filter([]);setLoading(true);
      }}>
        <option value="">Entire library</option>{workspaces.map(w => <option value={w.id} key={w.id}>{w.name}</option>)}
      </select></label>
      <label>Collection <select disabled={loading || busy} value={selected} onChange={e => {
        setSelected(e.target.value);filter([]);setLoading(true);
      }}>
        <option value="">All papers in scope</option>{collections.map(c => <option value={c.id} key={c.id}>{c.name} · {c.document_count}</option>)}
      </select></label>
    </div>
    <button className="secondary" aria-expanded={manageable} onClick={() => setManageable(!manageable)}>
      {manageable ? "Close collection management" : "Manage collections"}
    </button>
    {error && <p className="notice error" role="alert">{error}</p>}
    {loading && <p role="status">Loading papers in scope…</p>}
    {manageable && <div className="collection-manage">
      <form className="finding-actions" onSubmit={e => {e.preventDefault();void mutate(async () => {
        const collection = await api.createCollection(workspace, name.trim());
        setSelected(String(collection.id));setName("");filter([]);
      });}}>
        <label>New collection name <input maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
        <button disabled={busy || loading || !name.trim()}>Create collection</button>
      </form>
      {selected && <>
        <form className="finding-actions" onSubmit={e => {e.preventDefault();void mutate(() => api.renameCollection(selected, renamed.trim()));}}>
          <label>Collection name <input maxLength={120} value={renamed} onChange={e => setRenamed(e.target.value)} /></label>
          <button className="secondary" disabled={busy || loading || !renamed.trim()}>Rename collection</button>
        </form>
        <fieldset disabled={busy || loading}><legend>Collection membership</legend>
          {documents.filter(d => scoped === null || scoped.includes(d.id)).map(d => <label key={d.id}>
            <input type="checkbox" checked={members.includes(d.id)}
              onChange={e => {const add = e.target.checked;void mutate(() => api.collectionMembership(selected, d.id, add));}} /> {d.title}
          </label>)}
        </fieldset>
      </>}
    </div>}
  </section>;
}
