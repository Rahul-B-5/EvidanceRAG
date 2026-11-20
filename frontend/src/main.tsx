import { useEffect, useRef, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { api, type Document, type ImportJobRecord, type Workspace } from "./api";
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
import { LibraryCollections } from "./LibraryCollections";
import { SettingsView } from "./SettingsView";
import { ClaimExplorer, type ClaimLocation } from "./ClaimExplorer";
import "./styles.css";

const views = [
  ["dashboard", "Overview", "⌂"],
  ["library", "Library", "▤"],
  ["reader", "Reader", "▣"],
  ["assistant", "Assistant", "✧"],
  ["research", "Evidence & compare", "⌕"],
  ["compare", "Comparison studio", "▥"],
  ["claims", "Claim Explorer", "≡"],
  ["atlas", "Evidence Atlas", "⌘"],
  ["reproduction", "Reproducibility", "▧"],
  ["coverage", "Question coverage", "▦"],
  ["directions", "Research directions", "◇"],
  ["saved", "Saved evidence", "◇"],
  ["packets", "Evidence packets", "▱"],
  ["workspaces", "Workspaces", "⊞"],
  ["settings", "Settings", "⚙"],
] as const;
type View = typeof views[number][0];
const keptViews: View[] = ["library", "compare", "reproduction", "coverage", "directions", "packets"];
const navGroups: Array<[string, View[]]> = [
  ["Library", ["dashboard", "library", "reader", "workspaces"]],
  ["Investigate", ["assistant", "research", "compare", "claims", "atlas", "reproduction", "coverage", "directions"]],
  ["Write", ["saved", "packets"]],
  ["Preferences", ["settings"]],
];
type ImportJob = {id: string; name: string; file?: File; state: ImportJobRecord["state"];
  error?: string; documentId?: number; retryable?: boolean};
const importDisplay = (job: ImportJobRecord): ImportJob => ({
  id:job.id, name:job.filename, state:job.state, documentId:job.document_id ?? undefined,
  error:job.error ?? undefined, retryable:job.retryable,
});
const importLabels = {queued:"Queued", indexing:"Indexing", imported:"Imported", duplicate:"Already in library", failed:"Failed"};

function App() {
  const [view, setView] = useState<View>("dashboard");
  const [dark, setDark] = useState(() => localStorage.getItem("evidencerag.theme")
    ? localStorage.getItem("evidencerag.theme") === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [readerPage, setReaderPage] = useState(1);
  const [readerWorkspace, setReaderWorkspace] = useState("");
  const [findingQuestion, setFindingQuestion] = useState<FindingQuestion>();
  const [claimLocation, setClaimLocation] = useState<ClaimLocation>();
  const [atlasLocation, setAtlasLocation] = useState<ClaimLocation>();
  const [openedResearchViews, setOpenedResearchViews] = useState<Set<View>>(() => new Set());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [imports, setImports] = useState<ImportJob[]>([]);
  const [serverImports, setServerImports] = useState<ImportJob[]>([]);
  const [importError, setImportError] = useState("");
  const observedImports = useRef(new Set<string>());
  const importLock = useRef(false);
  const [command, setCommand] = useState("");
  const [mobileNavigation, setMobileNavigation] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
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
    setMobileNavigation(false);
    if (keptViews.includes(next)) {
      setOpenedResearchViews(previous => previous.has(next) ? previous : new Set([...previous, next]));
    }
    if (next === "assistant") setFindingQuestion(undefined);
    if (next === "claims") setClaimLocation(undefined);
    if (next === "atlas") setAtlasLocation(undefined);
    if (next === "dashboard") void refresh();
  }

  function openPaper(id: number) {
    setSelectedId(id);
    setReaderPage(1);
    setReaderWorkspace("");
    navigate("reader");
  }

  function askFinding(question: FindingQuestion) {
    setFindingQuestion(question);
    setView("assistant");
  }

  useEffect(() => { void refresh(); }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [view]);
  useEffect(() => {
    if (view !== "library") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      let delay = 1300;
      try {
        const result = await api.imports(controller.signal);
        if (controller.signal.aborted) return;
        setServerImports(result.jobs.map(importDisplay));
        setImportError("");
        const completed = result.jobs.filter(job => job.document_id && !observedImports.current.has(job.id));
        completed.forEach(job => observedImports.current.add(job.id));
        if (completed.length) void refresh();
        if (result.jobs.some(job => job.state === "queued" || job.state === "indexing")) delay = 500;
      } catch {
        if (!controller.signal.aborted) setImportError("Unable to refresh import jobs.");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, delay);
      }
    }
    void poll();
    return () => {controller.abort(); clearTimeout(timer);};
  }, [view]);
  useEffect(() => {
    const followCitation = () => {
      const match = /^#paper=(\d+)&page=(\d+)(?:&workspace=(\d+))?$/.exec(location.hash);
      const claim = /^#(claim|atlas)=(finding:[a-f0-9]{24})(?:&workspace=(\d+))?$/.exec(location.hash);
      const claimPaper = /^#claims-paper=(\d+)(?:&workspace=(\d+))?$/.exec(location.hash);
      if (match) {
        setSelectedId(Number(match[1]));
        setReaderPage(Number(match[2]));
        setReaderWorkspace(match[3] ?? "");
        setView("reader");
      } else if (claim?.[1] === "atlas") {
        setAtlasLocation({id:claim[2],workspace:claim[3]});
        setView("atlas");
      } else if (claim || claimPaper) {
        setClaimLocation({id:claim?.[2],workspace:claim?.[3] ?? claimPaper?.[2],paper:claimPaper?.[1]});
        setView("claims");
      } else return;
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

  async function runImports(jobs: ImportJob[]) {
    if (!jobs.length || importLock.current) return;
    importLock.current = true;
    setUploading(true);setError("");
    try {
      const ids = new Set(jobs.map(j => j.id));
      setImports(previous => [...jobs, ...previous.filter(job => !ids.has(job.id))]);
      for (const job of jobs) {
        if (!job.file) continue;
        setImports(previous => previous.map(j => j.id === job.id ? {...j, state:"indexing"} : j));
        try {
          const result = await api.upload(job.file);
          setImports(previous => previous.filter(j => j.id !== job.id));
          setServerImports(previous => [importDisplay(result), ...previous.filter(j => j.id !== result.id)]);
        } catch (e) {
          setImports(previous => previous.map(j => j.id === job.id
            ? {...j, state:"failed", error:e instanceof Error ? e.message : "Import failed."} : j));
        }
      }
    } finally {
      importLock.current = false;
      setUploading(false);
    }
  }

  async function retryImport(job: ImportJob) {
    if (job.file) {
      await runImports([{...job,state:"queued",error:undefined}]);
      return;
    }
    try {
      const retried = await api.retryImport(job.id);
      setServerImports(previous => previous.map(item => item.id === job.id ? importDisplay(retried) : item));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to retry import.");
    }
  }

  async function remove(d: Document) {
    if (!window.confirm(`Permanently delete “${d.title}”, its indexed passages, and its Reader bookmarks and highlight notes?`)) return;
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
  if (view === "reader") content = selected
    ? <Reader key={`${selected.id}-${readerPage}`} document={selected} initialPage={readerPage} workspace={readerWorkspace}
      update={paper => setDocuments(current => current.map(d => d.id === paper.id ? paper : d))} remove={() => void remove(selected)} />
    : loading ? <p role="status">Loading paper…</p>
    : <section className="panel empty"><h2>Select a paper to read</h2><button onClick={() => navigate("library")}>Open library</button></section>;
  else if (view === "assistant") content = <Conversations documents={documents} initial={findingQuestion} />;
  else if (view === "atlas") content = <EvidenceAtlas key={JSON.stringify(atlasLocation)} initial={atlasLocation} compare={() => navigate("compare")} ask={askFinding} />;
  else if (view === "claims") content = <ClaimExplorer key={JSON.stringify(claimLocation)} initial={claimLocation}
    documents={documents} workspaces={workspaces} ask={askFinding} />;
  else if (keptViews.includes(view)) content = null;
  else if (view === "saved") content = <SavedEvidence />;
  else if (view === "settings") content = <SettingsView />;
  else if (view === "research" || view === "workspaces") content = <WorkspaceArea key={view} documents={documents} manage={view === "workspaces"} />;
  else content = <section className="panel overview">
    <div className="overview-summary"><div><h2>Research library</h2><p>{documents.length} papers · {documents.reduce((n, d) => n + d.chunk_count, 0)} passages · {workspaces.length} workspaces</p></div>
      <button onClick={() => navigate("library")}>Open library</button></div>
    <h3>Recent papers</h3>
    {loading ? <p role="status">Loading papers…</p> : documents.length ? <PaperRows documents={documents.slice(0, 6)} openPaper={openPaper} /> : <p>Import a PDF from the library to start.</p>}
  </section>;

  return <div className="app">
    <a className="skip-link" href="#content">Skip to content</a>
    <aside className="app-sidebar" onKeyDown={event => {
      if (event.key === "Escape" && mobileNavigation) {
        setMobileNavigation(false);
        menuButton.current?.focus();
      }
    }}>
      <div className="app-sidebar-top">
        <div className="brand"><span aria-hidden="true">E</span> EvidenceRAG</div>
        <button ref={menuButton} className="secondary nav-toggle" aria-expanded={mobileNavigation} aria-controls="research-navigation"
          onClick={() => setMobileNavigation(open => !open)}>Menu</button>
      </div>
      <div className="app-shortcuts">
        <button className="command-trigger" onClick={() => {setCommand("");palette.current?.showModal();}}>Quick open <kbd>Ctrl/⌘ K</kbd></button>
        <button className="theme-toggle theme-mobile" onClick={() => setDark(!dark)}><span aria-hidden="true">◐</span>{dark ? "Light theme" : "Dark theme"}</button>
      </div>
      <nav id="research-navigation" aria-label="Research navigation" data-open={mobileNavigation}>{navGroups.map(([group, ids]) =>
        <div className="nav-group" key={group} role="group" aria-label={group}>
          <small aria-hidden="true">{group}</small>
          {ids.map(id => {
            const [,label, icon] = views.find(v => v[0] === id)!;
            return <button key={id} className="nav" aria-current={view === id ? "page" : undefined} onClick={() => navigate(id)}>
              <span aria-hidden="true">{icon}</span>{label}
            </button>;
          })}
        </div>)}</nav>
      <div className="app-sidebar-bottom"><button className="nav" onClick={() => setDark(!dark)}><span aria-hidden="true">◐</span>{dark ? "Light theme" : "Dark theme"}</button></div>
    </aside>
    <main id="content" className="shell">
      <header className="page-header"><h1>{title}</h1>
        {(view === "dashboard" || view === "library") && <button className="secondary" disabled={loading} onClick={() => void refresh()}>Refresh library</button>}
      </header>
      {error && <p className="notice error" role="alert">{error}</p>}
      {content}
      {openedResearchViews.has("library") && <div hidden={view !== "library"}>
        <Library documents={documents} workspaces={workspaces} active={view === "library"} loading={loading} uploading={uploading} imports={[...imports,...serverImports]} importError={importError}
          queue={files => void runImports(files.map(file => ({id:crypto.randomUUID(), name:file.name, file, state:"queued"})))}
          retry={job => void retryImport(job)} openPaper={openPaper} />
      </div>}
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
      <td><button className="paper-link" onClick={() => openPaper(d.id)}>{d.title}</button>
        <small>{[d.authors.join(", ") || d.filename, d.venue, d.publication_year].filter(Boolean).join(" · ")}</small>
        {!!d.tags.length && <small>{d.tags.join(" · ")}</small>}</td>
      <td>{d.page_count ?? "—"}</td><td><span className="tag">{d.processing_status}</span></td>
    </tr>)}</tbody>
  </table></div>;
}

function Library({documents, workspaces, active, loading, uploading, imports, importError, queue, retry, openPaper}: {
  documents: Document[]; workspaces: Workspace[]; active: boolean; loading: boolean; uploading: boolean; imports: ImportJob[];
  importError: string;
  queue: (files: File[]) => void; retry: (job: ImportJob) => void; openPaper: (id: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [scoped, setScoped] = useState<number[] | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const visible = documents.filter(d => (scoped === null || scoped.includes(d.id)) && [d.title, d.filename, d.venue ?? "", d.doi ?? "", ...d.authors, ...d.tags]
    .some(text => text.toLowerCase().includes(query.trim().toLowerCase())));
  if (sort === "title") visible.sort((a, b) => a.title.localeCompare(b.title));
  if (sort === "year") visible.sort((a, b) => (b.publication_year ?? 0) - (a.publication_year ?? 0));
  return <section className="panel library-panel">
    <div className="library-heading">
      <div><h2>Papers</h2><p className="muted">{visible.length} {visible.length === 1 ? "paper" : "papers"}</p></div>
      <input ref={input} type="file" accept=".pdf,application/pdf" multiple hidden onChange={e => {
        const files = Array.from(e.target.files ?? []);
        e.target.value = "";
        queue(files);
      }} />
      <button disabled={uploading} onClick={() => input.current?.click()}>{uploading ? "Import in progress…" : "Import PDFs"}</button>
    </div>
    <LibraryCollections documents={documents} workspaces={workspaces} filter={setScoped} visible={active} />
    <div className="library-controls">
      <label>Filter papers<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Title, author, venue, DOI or tag" /></label>
      <label>Sort by<select value={sort} onChange={e => setSort(e.target.value)}><option value="recent">Recently added</option><option value="title">Title</option><option value="year">Publication year</option></select></label>
    </div>
    {loading ? <p role="status">Loading library…</p> : visible.length ? <PaperRows documents={visible} openPaper={openPaper} />
      : <p className="empty">{query || scoped !== null ? "No papers match the current scope and filter." : "Your library is empty. Import a PDF to begin."}</p>}
    {importError && <p role="alert">{importError}</p>}
    {!!imports.length && <section className="import-queue" aria-label="PDF import queue">
      <h2>Import queue</h2>
      <ul>{imports.map(job => <li key={job.id}>
        <span>{job.name}</span><span role="status">{importLabels[job.state]}{job.error ? ` · ${job.error}` : ""}</span>
        {job.state === "failed" && (job.file || job.retryable) && <button className="secondary" disabled={uploading} onClick={() => retry(job)}>Retry</button>}
        {job.documentId && <button className="secondary" disabled={uploading} onClick={() => openPaper(job.documentId!)}>Open paper</button>}
      </li>)}</ul>
    </section>}
  </section>;
}

createRoot(document.getElementById("root")!).render(<App />);
