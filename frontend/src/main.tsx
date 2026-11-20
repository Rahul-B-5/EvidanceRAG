import { useEffect, useRef, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { api, type Document, type Workspace } from "./api";
import { WorkspaceArea } from "./WorkspaceArea";
import { Conversations } from "./Conversations";
import { Reader } from "./Reader";
import { SavedEvidence } from "./SavedEvidence";
import type { FindingQuestion } from "./ComparisonStudio";
import { EvidenceAtlas } from "./EvidenceAtlas";
import { ReproductionStudio } from "./ReproductionStudio";
import { ResearchCoverage } from "./ResearchCoverage";
import { ResearchDirectionStudio } from "./ResearchDirections";
import { EvidencePackets } from "./EvidencePackets";
import "./styles.css";

const views = [
  ["dashboard", "Overview", "⌂"],
  ["library", "Library", "▤"],
  ["reader", "Reader", "▣"],
  ["assistant", "Assistant", "✧"],
  ["research", "Evidence & compare", "⌕"],
  ["compare", "Comparison studio", "▥"],
  ["atlas", "Evidence Atlas", "⌘"],
  ["reproduction", "Reproducibility", "▧"],
  ["coverage", "Question coverage", "▦"],
  ["directions", "Research directions", "◇"],
  ["saved", "Saved evidence", "◇"],
  ["packets", "Evidence packets", "▱"],
  ["workspaces", "Workspaces", "⊞"],
] as const;
type View = typeof views[number][0];

function App() {
  const [view, setView] = useState<View>("dashboard");
  const [dark, setDark] = useState(() => localStorage.getItem("evidencerag.theme")
    ? localStorage.getItem("evidencerag.theme") === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [readerPage, setReaderPage] = useState(1);
  const [findingQuestion, setFindingQuestion] = useState<FindingQuestion>();
  const [openedResearchViews, setOpenedResearchViews] = useState<Set<View>>(() => new Set());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const [command, setCommand] = useState("");
  const palette = useRef<HTMLDialogElement>(null);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [library, groups] = await Promise.all([api.documents(), api.workspaces()]);
      setDocuments(library.documents);
      setWorkspaces(groups.workspaces);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach EvidenceRAG.");
    } finally {
      setLoading(false);
    }
  }

  function navigate(next: View) {
    setView(next);
    setNotice("");
    if (next === "compare" || next === "reproduction" || next === "coverage" || next === "directions" || next === "packets") {
      setOpenedResearchViews(previous => previous.has(next) ? previous : new Set([...previous, next]));
    }
    if (next === "assistant") setFindingQuestion(undefined);
    if (next === "dashboard") void refresh();
  }

  function openPaper(id: number) {
    setSelectedId(id);
    setReaderPage(1);
    navigate("reader");
  }

  function askFinding(question: FindingQuestion) {
    setFindingQuestion(question);
    setView("assistant");
  }

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    const followCitation = () => {
      const match = /^#paper=(\d+)&page=(\d+)$/.exec(location.hash);
      if (!match) return;
      setSelectedId(Number(match[1]));
      setReaderPage(Number(match[2]));
      setView("reader");
      history.replaceState(null, "", location.pathname + location.search);
    };
    followCitation();
    window.addEventListener("hashchange", followCitation);
    return () => window.removeEventListener("hashchange", followCitation);
  }, []);
  useEffect(() => {
    localStorage.setItem("evidencerag.theme", dark ? "dark" : "light");
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);
  useEffect(() => {
    const shortcut = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const dialog = palette.current;
        if (dialog?.open) dialog.close();
        else {
          setCommand("");
          dialog?.showModal();
        }
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  const selected = documents.find(d => d.id === selectedId);
  const title = views.find(([id]) => id === view)?.[1];
  const commands = [
    ...views.map(([id, label]) => ({key: id, label, run: () => navigate(id)})),
    ...documents.map(d => ({key: `paper-${d.id}`, label: d.title, run: () => openPaper(d.id)})),
  ].filter(item => item.label.toLowerCase().includes(command.trim().toLowerCase())).slice(0, 12);

  async function upload(file: File) {
    setUploading(true); setError(""); setNotice("");
    try {
      const result = await api.upload(file);
      setNotice(result.status === "already_exists" ? "Paper already in your library. Its source is available." : "Paper indexed and ready to read.");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function remove(d: Document) {
    if (!window.confirm(`Permanently delete “${d.title}” and its indexed passages?`)) return;
    setError("");
    try {
      await api.remove(d.id);
      setSelectedId(null);
      navigate("library");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deletion failed.");
    }
  }

  let content: ReactNode;
  if (view === "library") content = <Library documents={documents} loading={loading} uploading={uploading} upload={upload} openPaper={openPaper} />;
  else if (view === "reader") content = selected
    ? <Reader key={`${selected.id}-${readerPage}`} document={selected} initialPage={readerPage} remove={() => void remove(selected)} />
    : loading ? <p role="status">Loading paper…</p>
    : <section className="panel empty"><h2>Select a paper to read</h2><button onClick={() => navigate("library")}>Open library</button></section>;
  else if (view === "assistant") content = <Conversations documents={documents} initial={findingQuestion} />;
  else if (view === "atlas") content = <EvidenceAtlas compare={() => navigate("compare")} ask={askFinding} />;
  else if (view === "compare" || view === "reproduction" || view === "coverage" || view === "directions" || view === "packets") content = null;
  else if (view === "saved") content = <SavedEvidence />;
  else if (view === "research" || view === "workspaces") content = <WorkspaceArea key={view} documents={documents} manage={view === "workspaces"} />;
  else content = <section className="panel overview">
    <div className="overview-summary"><div><h2>Research library</h2><p>{documents.length} papers · {documents.reduce((n, d) => n + d.chunk_count, 0)} passages · {workspaces.length} workspaces</p></div>
      <button onClick={() => navigate("library")}>Open library</button></div>
    <h3>Recent papers</h3>
    {loading ? <p role="status">Loading papers…</p> : documents.length ? <PaperRows documents={documents.slice(0, 6)} openPaper={openPaper} /> : <p>Import a PDF from the library to start.</p>}
  </section>;

  return <div className="app">
    <a className="skip-link" href="#content">Skip to content</a>
    <aside className="sidebar">
      <div className="brand"><span aria-hidden="true">E</span> EvidenceRAG</div>
      <button className="command-trigger" onClick={() => {setCommand("");palette.current?.showModal();}}>Quick open <kbd>Ctrl/⌘ K</kbd></button>
      <nav aria-label="Research navigation">{views.map(([id, label, icon]) =>
        <button key={id} className="nav" aria-current={view === id ? "page" : undefined} onClick={() => navigate(id)}>
          <span aria-hidden="true">{icon}</span>{label}
        </button>)}</nav>
      <div className="sidebar-bottom"><button className="nav" onClick={() => setDark(!dark)}><span aria-hidden="true">◐</span>{dark ? "Light theme" : "Dark theme"}</button></div>
    </aside>
    <main id="content" className="shell">
      <header className="page-header"><h1>{title}</h1><button className="secondary" disabled={loading} onClick={() => void refresh()}>Refresh library</button></header>
      {error && <p className="notice error" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      {content}
      {openedResearchViews.has("compare") && <div hidden={view !== "compare"}><WorkspaceArea documents={documents} compare={askFinding} /></div>}
      {openedResearchViews.has("reproduction") && <div hidden={view !== "reproduction"}><ReproductionStudio documents={documents} workspaces={workspaces} /></div>}
      {openedResearchViews.has("coverage") && <div hidden={view !== "coverage"}><ResearchCoverage workspaces={workspaces} ask={askFinding} /></div>}
      {openedResearchViews.has("directions") && <div hidden={view !== "directions"}><ResearchDirectionStudio workspaces={workspaces} ask={askFinding} /></div>}
      {openedResearchViews.has("packets") && <div hidden={view !== "packets"}><EvidencePackets workspaces={workspaces} /></div>}
    </main>
    <dialog ref={palette} className="palette" aria-label="Quick open">
      <form onSubmit={e => {e.preventDefault(); if (commands[0]) {palette.current?.close();commands[0].run();}}}>
        <label>Go to a view or paper<input autoFocus value={command} onChange={e => setCommand(e.target.value)} placeholder="Search commands…" /></label>
      </form>
      <div className="command-results">
        {commands.map(item => <button key={item.key} onClick={() => {palette.current?.close();item.run();}}>{item.label}</button>)}
        {!commands.length && <p>No matching commands.</p>}
      </div>
      <button className="secondary" onClick={() => palette.current?.close()}>Close</button>
    </dialog>
  </div>;
}

function PaperRows({documents, openPaper}: {documents: Document[]; openPaper: (id: number) => void}) {
  return <div className="table-scroll"><table className="paper-table">
    <thead><tr><th scope="col">Paper</th><th scope="col">Pages</th><th scope="col">Status</th></tr></thead>
    <tbody>{documents.map(d => <tr key={d.id}>
      <td><button className="paper-link" onClick={() => openPaper(d.id)}>{d.title}</button><small>{d.authors?.join(", ") || d.filename}</small></td>
      <td>{d.page_count ?? "—"}</td><td><span className="tag">{d.processing_status}</span></td>
    </tr>)}</tbody>
  </table></div>;
}

function Library({documents, loading, uploading, upload, openPaper}: {
  documents: Document[]; loading: boolean; uploading: boolean;
  upload: (file: File) => Promise<void>; openPaper: (id: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const input = useRef<HTMLInputElement>(null);
  const visible = documents.filter(d => [d.title, d.filename, ...d.authors]
    .some(text => text.toLowerCase().includes(query.trim().toLowerCase())));
  if (sort === "title") visible.sort((a, b) => a.title.localeCompare(b.title));
  return <section className="panel">
    <div className="library-controls">
      <label>Filter papers<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Title, filename or author" /></label>
      <label>Sort by<select value={sort} onChange={e => setSort(e.target.value)}><option value="recent">Recently added</option><option value="title">Title</option></select></label>
      <input ref={input} type="file" accept=".pdf,application/pdf" hidden onChange={e => {
        const file = e.target.files?.[0];
        e.target.value = "";
        if (file) void upload(file);
      }} />
      <button disabled={uploading} onClick={() => input.current?.click()}>{uploading ? "Indexing PDF…" : "Import PDF"}</button>
    </div>
    {loading ? <p role="status">Loading library…</p> : visible.length ? <PaperRows documents={visible} openPaper={openPaper} />
      : <p className="empty">{query ? "No matching papers." : "Your library is empty. Import a PDF to begin."}</p>}
  </section>;
}

createRoot(document.getElementById("root")!).render(<App />);
