import { useEffect, useState } from "react";
import { api, type EvidencePacket, type PacketSummary, type SavedPassage, type Workspace } from "./api";
import { downloadPacket, type PacketFormat } from "./packetExport";

const formats: Array<[PacketFormat, string]> = [["md","Markdown"],["html","HTML"],["json","JSON"],["bib","BibTeX"]];

function PacketEditor({packet, update}: {packet: EvidencePacket; update: (packet: EvidencePacket) => void}) {
  const [title, setTitle] = useState(packet.title);
  const [question, setQuestion] = useState(packet.question);
  const [narrative, setNarrative] = useState(packet.narrative);
  const [format, setFormat] = useState<PacketFormat>("md");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const dirty = title !== packet.title || question !== packet.question || narrative !== packet.narrative;

  async function save() {
    setBusy(true);setError("");setMessage("");
    try {
      const saved = await api.editPacket(packet.id, {title, question, narrative, revision:packet.revision});
      setTitle(saved.title);setQuestion(saved.question);setNarrative(saved.narrative);
      update(saved);setMessage("Briefing saved.");
    } catch(e) {
      setError(e instanceof Error ? e.message : "Unable to save briefing.");
    } finally {
      setBusy(false);
    }
  }
  async function draft() {
    setBusy(true);setError("");setMessage("");
    try {
      const result = await api.draftPacket(packet.id);
      if (result.abstained) setMessage(result.reason ?? "The provider abstained.");
      else {
        setNarrative(result.answer);
        setMessage("Draft inserted. Review its claims and source references before saving.");
      }
    } catch(e) {
      setError(e instanceof Error ? e.message : "Unable to draft briefing.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="research-controls">
    <section className="panel plan-editor">
      <h2>Research briefing</h2>
      <form onSubmit={e => {e.preventDefault();void save();}}>
        <label>Packet title<input value={title} disabled={busy} maxLength={160} onChange={e => setTitle(e.target.value)} /></label>
        <label>Research question<textarea value={question} disabled={busy} maxLength={1500} rows={3} onChange={e => setQuestion(e.target.value)} /></label>
        <label>Briefing text<textarea value={narrative} disabled={busy} maxLength={30000} rows={12} onChange={e => setNarrative(e.target.value)}
          placeholder="Use [E1], [E2] and the other packet IDs to cite source snapshots." /></label>
        <div className="finding-actions">
          <button disabled={busy || !dirty || !title.trim()}>Save briefing</button>
          <button type="button" className="secondary" onClick={() => void draft()} disabled={busy || dirty || !!narrative || packet.items.length > 16}>Draft with provider</button>
        </div>
      </form>
      <p className="muted">Drafting uses the saved question and up to 16 passage snapshots. The configured provider receives these excerpts.</p>
      {message && <p role="status">{message}</p>}
      {error && <p className="notice error" role="alert">{error}</p>}
      <div className="finding-actions">
        <label>Export format <select value={format} onChange={e => setFormat(e.target.value as PacketFormat)}>
          {formats.map(([ext, label]) => <option key={ext} value={ext}>{label}</option>)}
        </select></label>
        <button className="secondary" disabled={busy} onClick={() => downloadPacket({...packet, title, question, narrative}, format)}>Export evidence packet</button>
      </div>
    </section>
    <section className="panel">
      <h2>Source snapshots</h2>
      {packet.items.map((item, index) => <details key={item.chunk_id} className="check-row dossier-item">
        <summary>[E{index + 1}] {item.title} · p. {item.page_start}</summary>
        <article className="finding-card"><blockquote>{item.passage}</blockquote>
          {item.note && <p>{item.note}</p>}
          <a href={`#paper=${item.document_id}&page=${item.page_start}`}>Open source</a>
        </article>
      </details>)}
    </section>
  </div>;
}

export function EvidencePackets({workspaces}: {workspaces: Workspace[]}) {
  const [workspace, setWorkspace] = useState("");
  const [saved, setSaved] = useState<SavedPassage[] | null>(null);
  const [packets, setPackets] = useState<PacketSummary[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [packet, setPacket] = useState<EvidencePacket | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setSaved(null);setError("");setPackets([]);
    Promise.all([api.savedEvidence(), api.packets(workspace), workspace ? api.workspace(Number(workspace)) : Promise.resolve(null)])
      .then(([notebook, history, scope]) => {
        if (!active) return;
        const ids = scope && new Set(scope.documents.map(x => x.id));
        setSaved(notebook.items.filter(item => !ids || ids.has(item.document_id)));
        setPackets(history.packets);
      }).catch(e => {if (active) setError(e instanceof Error ? e.message : "Unable to load evidence packets.");});
    return () => {active = false;};
  }, [workspace, refresh]);

  async function create() {
    setBusy(true);setError("");
    try {
      const created = await api.createPacket(workspace, title.trim(), selected);
      setPacket(created);setSelected([]);setTitle("");setRefresh(n => n + 1);
    } catch(e) {
      setError(e instanceof Error ? e.message : "Unable to create evidence packet.");
    } finally {
      setBusy(false);
    }
  }
  async function open(id: string) {
    if (!id) return;
    setBusy(true);setError("");
    try {
      setPacket(await api.packet(id));
    } catch(e) {
      setError(e instanceof Error ? e.message : "Unable to open evidence packet.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="research-tools">
    <div className="panel atlas-toolbar dossier-controls">
      <label>Workspace <select value={workspace} disabled={busy} onChange={e => {setWorkspace(e.target.value);setPacket(null);setSelected([]);}}>
        <option value="">Library packets</option>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select></label>
      <label>Saved packet <select value={packet?.id ?? ""} disabled={busy} onChange={e => {if (!e.target.value) setPacket(null); else void open(e.target.value);}}>
        <option value="">New evidence packet</option>{packets.map(p => <option key={p.id} value={p.id}>{p.title} · {p.item_count} passages</option>)}
      </select></label>
      <div><button className="secondary" disabled={busy} onClick={() => setRefresh(n => n + 1)}>Refresh saved passages</button></div>
    </div>
    {error && <p role="alert" className="notice error">{error}</p>}
    {packet ? <PacketEditor key={packet.id} packet={packet} update={next => {setPacket(next);setRefresh(n => n + 1);}} />
      : <form className="panel comparison-setup" onSubmit={e => {e.preventDefault();void create();}}>
        <h2>Assemble a packet</h2><label>Packet title<input maxLength={160} disabled={busy} value={title} onChange={e => setTitle(e.target.value)} /></label>
        {!saved && !error && <p role="status">Loading saved passages…</p>}
        {saved?.length === 0 && <p>Save passages from Reader or the Evidence Atlas before assembling a packet.</p>}
        {!!saved?.length && <fieldset aria-label="Saved passages" disabled={busy}>
          {saved.map(item => <label key={item.chunk_id}>
            <input type="checkbox" checked={selected.includes(item.chunk_id)} disabled={selected.length >= 50 && !selected.includes(item.chunk_id)}
              onChange={e => setSelected(ids => e.target.checked ? [...ids, item.chunk_id] : ids.filter(id => id !== item.chunk_id))} />
            <span>{item.title} · p. {item.page_start}<small className="packet-excerpt">{item.passage.slice(0, 170)}</small></span>
          </label>)}
        </fieldset>}
        <div><button disabled={busy || !title.trim() || !selected.length}>Create evidence packet</button></div>
      </form>}
  </div>;
}
