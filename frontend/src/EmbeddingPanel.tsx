import { useEffect, useState } from "react";
import { api, type EmbeddingStatus } from "./api";

export function EmbeddingPanel({documentId}: {documentId: number}) {
  const [opened, setOpened] = useState(false);
  const [status, setStatus] = useState<EmbeddingStatus>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const active = status?.job?.status === "running" || status?.job?.status === "queued";

  useEffect(() => {
    if (!opened) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const next = await api.embeddingStatus(documentId, controller.signal);
        if (controller.signal.aborted) return;
        setStatus(next);
        setError("");
        if (next.job?.status === "queued" || next.job?.status === "running") timer = setTimeout(load, 900);
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Unable to check embeddings.");
      }
    }
    void load();
    return () => {controller.abort(); clearTimeout(timer);};
  }, [documentId, opened, refresh]);

  async function change(cancel: boolean) {
    if (!status) return;
    setBusy(true);
    setError("");
    try {
      if (cancel && status.job) await api.cancelRebuild(documentId, status.job.id);
      else setStatus({...status, job:await api.rebuildEmbeddings(documentId)});
      setRefresh(value => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update embeddings.");
    } finally { setBusy(false); }
  }

  return <details className="reader-embeddings" onToggle={e => setOpened(e.currentTarget.open)}>
    <summary>Search embeddings</summary>
    {error && <div className="finding-actions"><p role="alert">{error}</p><button type="button" className="secondary"
      onClick={() => {setError(""); setRefresh(value => value + 1);}}>Refresh status</button></div>}
    {!status && !error && opened && <p role="status">Checking embeddings…</p>}
    {status && <>
      <p>{status.active_chunks} of {status.total_chunks} passages match the active embedding profile.</p>
      <small>{status.model} · {status.dimensions} dimensions</small>
      {status.job && <p role="status">{active ? `${status.job.prepared_chunks} of ${status.job.total_chunks} replacement vectors prepared`
        : status.job.status === "completed" ? "Embedding rebuild complete."
          : status.job.status === "cancelled" ? "Embedding rebuild cancelled." : status.job.error ?? "Embedding rebuild ended."}</p>}
      {active && status.job && <progress aria-label="Embedding rebuild progress" max={status.job.total_chunks} value={status.job.prepared_chunks} />}
      <div className="finding-actions">
        {active
          ? <button type="button" className="secondary" disabled={busy} onClick={() => void change(true)}>Cancel rebuild</button>
          : <button type="button" className="secondary" disabled={busy || !status.total_chunks} onClick={() => void change(false)}>Rebuild embeddings</button>}
      </div>
    </>}
  </details>;
}
