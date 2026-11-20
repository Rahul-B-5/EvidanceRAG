import { useEffect, useRef, useState } from "react";
import { api, type RuntimeSettings } from "./api";

const labels: Record<string, string> = {
  gemini:"Google Gemini", openai:"OpenAI", "openai-compatible":"OpenAI-compatible", ollama:"Ollama",
};

export function SettingsView() {
  const [data, setData] = useState<RuntimeSettings>();
  const [loadError, setLoadError] = useState("");
  const [revision, setRevision] = useState(0);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState("");
  const [elapsed, setElapsed] = useState<number>();
  const probe = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.runtimeSettings(controller.signal).then(value => {
      if (!controller.signal.aborted) {setData(value); setLoadError("");}
    }).catch(err => {
      if (!controller.signal.aborted) setLoadError(err instanceof Error ? err.message : "Unable to load diagnostics.");
    });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => () => probe.current?.abort(), []);

  async function testProvider() {
    const controller = new AbortController();
    probe.current = controller;
    setProbing(true);
    setProbeError("");
    setElapsed(undefined);
    try {
      const result = await api.testProvider(controller.signal);
      if (!controller.signal.aborted) setElapsed(result.elapsed_ms);
    } catch (err) {
      if (!controller.signal.aborted) setProbeError(err instanceof Error ? err.message : "Provider check failed.");
    } finally {
      if (!controller.signal.aborted) setProbing(false);
    }
  }

  return <div className="research-tools">
    <div className="finding-actions"><button className="secondary" onClick={() => setRevision(value => value + 1)}>Refresh diagnostics</button></div>
    {loadError && <p role="alert" className="notice error">{loadError}</p>}
    {!data && !loadError && <p role="status">Loading diagnostics…</p>}
    {data && <div className="settings-grid">
      <section className="panel">
        <div className="comparison-heading"><h2>Generation</h2><span className="tag">{data.generation.configured ? "Configured" : "Needs configuration"}</span></div>
        <dl>
          <div><dt>Provider</dt><dd>{data.generation.provider ? labels[data.generation.provider] : "Unrecognized"}</dd></div>
          <div><dt>Model</dt><dd>{data.generation.model ?? "Unspecified"}</dd></div>
          <div><dt>Processing</dt><dd>{data.generation.transport === "local" ? "Local" : data.generation.transport === "remote" ? "Remote" : "Unavailable"}</dd></div>
          <div><dt>Timeout</dt><dd>{data.generation.timeout_seconds} seconds</dd></div>
        </dl>
        <p>{data.generation.transport === "remote"
          ? "Generation workflows send the question and relevant excerpts to the configured provider."
          : "Model settings come from the server environment."}</p>
        <div className="finding-actions"><button disabled={!data.generation.configured || probing}
          onClick={() => void testProvider()}>{probing ? "Checking provider…" : "Test provider"}</button>
          <small>Uses a synthetic prompt.</small></div>
        {elapsed !== undefined && <p className="notice" role="status">Provider check passed in {elapsed.toLocaleString()} ms.</p>}
        {probeError && <p role="alert" className="notice error">{probeError}</p>}
      </section>
      <section className="panel">
        <div className="comparison-heading"><h2>Search index</h2><span className="tag">{data.database_connected ? "PostgreSQL connected" : "PostgreSQL unavailable"}</span></div>
        <dl>
          <div><dt>Model</dt><dd>{data.index.model}</dd></div>
          <div><dt>Dimensions</dt><dd>{data.index.dimensions}</dd></div>
          {data.database_connected && <>
            <div><dt>Papers</dt><dd>{data.index.papers}</dd></div>
            <div><dt>Active vectors</dt><dd>{data.index.compatible_vectors} of {data.index.passages} passages</dd></div>
          </>}
        </dl>
        {data.database_connected && data.index.compatible_vectors !== data.index.passages &&
          <p>Open a paper in Reader and use <strong>Search embeddings</strong> to rebuild vectors for this profile.</p>}
      </section>
    </div>}
  </div>;
}
