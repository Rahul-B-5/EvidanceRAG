import { useState } from "react";
import { api, type Comparison, type Document, type Evidence } from "./api";
import "./research.css";
import { SavePassage } from "./SavedEvidence";

function Passages({ evidence, documents }: { evidence: Evidence[]; documents: Document[] }) {
  return <div className="research-passages">{evidence.map(item => <article key={item.chunk_id}>
    <strong>{item.title}</strong>
    <p>{item.text}</p>
    {documents.find(d => d.id === item.document_id)?.has_stored_source
      ? <a href={`#paper=${item.document_id}&page=${item.page_start}`}>Open source · page {item.page_start}{item.page_end !== item.page_start ? `–${item.page_end}` : ""}</a>
      : <a href={`#paper=${item.document_id}&page=${item.page_start}`}>Read indexed passage · page {item.page_start}</a>}
    <small>Chunk {item.chunk_id}</small>
    <SavePassage id={item.chunk_id} />
  </article>)}</div>;
}

export function ResearchTools({ documents, workspaceId }: { documents: Document[]; workspaceId?: number }) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [evidence, setEvidence] = useState<Evidence[] | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(mode: "search" | "compare") {
    setBusy(true); setError(""); setComparison(null); setEvidence(null);
    try {
      if (mode === "search") setEvidence((await api.search(query.trim(), scope ? Number(scope) : undefined, workspaceId)).evidence);
      else setComparison(await api.compare(selected, workspaceId));
    } catch (e) { setError(e instanceof Error ? e.message : "Request failed."); }
    finally { setBusy(false); }
  }

  return <div className="research-tools">
    <p>Explore source passages and compare papers without an AI provider.</p>
    <div className="research-controls">
      <form className="panel" onSubmit={e => { e.preventDefault(); void run("search"); }}>
        <h2>Search evidence</h2>
        <label>Research question<input required value={query} onChange={e => setQuery(e.target.value)} placeholder="What datasets were used?" /></label>
        <label>Source scope<select value={scope} onChange={e => setScope(e.target.value)}>
          <option value="">{workspaceId ? "All workspace papers" : "Entire library"}</option>{documents.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
        </select></label>
        <button disabled={busy || !query.trim()}>Find passages</button>
      </form>
      <section className="panel">
        <h2>Compare evidence</h2><p>Select two to twelve papers.</p>
        <fieldset disabled={busy} aria-label="Papers to compare">{documents.map(d => <label key={d.id}>
          <input type="checkbox" checked={selected.includes(d.id)} onChange={e => setSelected(ids => e.target.checked ? [...ids, d.id] : ids.filter(id => id !== d.id))} />{d.title}
        </label>)}</fieldset>
        <button disabled={busy || selected.length < 2 || selected.length > 12} onClick={() => void run("compare")}>Compare selected papers</button>
      </section>
    </div>
    {busy && <p role="status">Retrieving passages…</p>}
    {error && <p role="alert" className="notice error">{error}</p>}
    {evidence && <section className="panel"><h2>{evidence.length} evidence passages</h2>{!evidence.length && <p>No passages found. Try another query or source scope.</p>}<Passages evidence={evidence} documents={documents} /></section>}
    {comparison && <section className="panel">
      <h2>Comparison evidence</h2><p>{comparison.notice} Missing means no passage matched the query; it does not establish that the paper omits the topic. Experimental conditions have not been assessed for comparability.</p>
      <div className="comparison-scroll"><table><thead><tr><th>Topic</th>{comparison.papers.map(p => <th key={p.document_id}>{p.title}</th>)}</tr></thead>
        <tbody>{comparison.fields.map(field => <tr key={field}><th scope="row">{field}</th>{comparison.papers.map(p => <td key={p.document_id}>{p.fields[field].evidence.length ? <Passages evidence={p.fields[field].evidence} documents={documents} /> : <span>No matching passage</span>}</td>)}</tr>)}</tbody>
      </table></div>
    </section>}
  </div>;
}
