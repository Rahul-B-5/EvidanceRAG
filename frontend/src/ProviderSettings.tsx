import { useEffect, useState } from "react";
import { api, type ProviderKind, type ProviderProfile, type ProviderProfiles, type ProviderPurpose } from "./api";

const names: Record<ProviderKind, string> = {
  ollama:"Ollama", openai:"OpenAI", anthropic:"Anthropic Claude", gemini:"Google Gemini",
  "openai-compatible":"OpenAI-compatible",
};
const purposes: Record<ProviderPurpose, string> = {answer:"Answering", extraction:"Structured extraction"};

export function ProviderSettings({refresh}: {refresh: () => void}) {
  const [profiles, setProfiles] = useState<ProviderProfiles>();
  const [purpose, setPurpose] = useState<ProviderPurpose>("answer");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.providerProfiles().then(value => {if (active) setProfiles(value);})
      .catch(e => {if (active) setError(String(e.message ?? e));});
    return () => {active = false;};
  }, []);

  return <section className="panel provider-settings" aria-labelledby="provider-settings-title">
    <h2 id="provider-settings-title">AI Providers</h2>
    {error && <p role="alert">{error}</p>}
    {!profiles && !error && <p role="status">Loading providers…</p>}
    {profiles && <>
      <div className="finding-actions" aria-label="Generation task">
        {Object.entries(purposes).map(([key,label]) =>
          <button key={key} className="secondary" aria-pressed={purpose === key}
            onClick={() => setPurpose(key as ProviderPurpose)}>{label}</button>)}
      </div>
      <ProfileForm key={purpose} purpose={purpose} initial={profiles[purpose]} onSave={profile => {
        setProfiles(current => current && {...current, [purpose]:profile});
        refresh();
      }} />
    </>}
  </section>;
}

function ProfileForm({purpose, initial, onSave}: {
  purpose: ProviderPurpose; initial: ProviderProfile | null; onSave: (value: ProviderProfile) => void;
}) {
  const [saved, setSaved] = useState(initial);
  const [provider, setProvider] = useState<ProviderKind>(initial?.provider ?? "ollama");
  const [model, setModel] = useState(initial?.model ?? "");
  const [endpoint, setEndpoint] = useState(initial?.endpoint ?? "");
  const [contextTokens, setContextTokens] = useState(initial?.ollama_context_tokens?.toString() ?? "");
  const [key, setKey] = useState("");
  const [models, setModels] = useState<string[]>();
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (provider !== "ollama") return;
    const controller = new AbortController();
    const start = window.setTimeout(() => {
      setConnecting(true);setConnectionError("");
      api.ollamaModels(endpoint, controller.signal).then(value => {
        if (controller.signal.aborted) return;
        setModels(value.models);
        setModel(current => current || value.models[0] || "");
      }).catch(e => {
        if (!controller.signal.aborted) {setModels(undefined);setConnectionError(String(e.message ?? e));}
      }).finally(() => {if (!controller.signal.aborted) setConnecting(false);});
    }, 300);
    return () => {window.clearTimeout(start);controller.abort();};
  }, [provider, endpoint, retry]);

  async function submit(test: boolean) {
    const contextSize = provider === "ollama" && contextTokens ? Number(contextTokens) : null;
    if (contextSize !== null && (!Number.isInteger(contextSize) || contextSize < 2048 || contextSize > 65536)) {
      setStatus("");setError("Enter a context size from 2,048 to 65,536 tokens.");
      return;
    }
    setBusy(true);setError("");setStatus("");
    const draft = {provider, model:model.trim(), endpoint, revision:saved?.revision ?? 0,
      ollama_context_tokens: contextSize,
      ...(key ? {api_key:key} : {})};
    try {
      if (test) {
        await api.testProviderProfile(purpose, draft);
        setStatus("Connection passed.");
      } else {
        const profile = await api.saveProviderProfile(purpose, draft);
        setSaved(profile);setKey("");setEndpoint(profile.endpoint);
        onSave(profile);setStatus("Provider saved and active.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the provider.");
    } finally {setBusy(false);}
  }

  return <form onSubmit={e => {e.preventDefault();void submit(false);}}>
    <p className="muted">{saved ? `Active model · ${saved.model}` :
      purpose === "extraction" ? "Uses the answering provider until an extraction model is saved." : "Choose a provider to override the server default."}</p>
    <div className="research-controls">
      <label>Provider<select disabled={busy} value={provider} onChange={e => {
        setProvider(e.target.value as ProviderKind);setModel("");setEndpoint("");setContextTokens("");setModels(undefined);
        setConnectionError("");setKey("");setStatus("");setError("");
      }}>{Object.entries(names).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Model identifier<input required disabled={busy} list={provider === "ollama" ? "installed-ollama-models" : undefined}
        value={model} onChange={e => setModel(e.target.value)} autoComplete="off" /></label>
    </div>
    {provider === "ollama" && <>
      <datalist id="installed-ollama-models">{models?.map(item => <option key={item} value={item} />)}</datalist>
      <div className="finding-actions">
        <span role="status">{connecting ? "Finding Ollama models…" : models ? (models.length ? `Ollama connected · ${models.length} installed models` : "Ollama connected · no installed models") : connectionError}</span>
        <button type="button" className="secondary" disabled={busy || connecting} onClick={() => setRetry(value => value + 1)}>Refresh models</button>
      </div>
      <details><summary>Advanced connection</summary>
        <label>Ollama endpoint<input disabled={busy} value={endpoint} placeholder="http://127.0.0.1:11434"
          onChange={e => setEndpoint(e.target.value)} /></label>
        <label>Context size in tokens<input type="number" min={2048} max={65536} step={1}
          disabled={busy} placeholder="Ollama default" value={contextTokens} aria-describedby="ollama-context-help"
          onChange={e => setContextTokens(e.target.value)} /></label>
        <p id="ollama-context-help" className="muted">A larger context fits more evidence and uses more memory. Leave blank to use Ollama's default.</p>
      </details>
    </>}
    {provider === "openai-compatible" && <label>Endpoint<input required disabled={busy} value={endpoint}
      placeholder="https://example.com/v1" onChange={e => setEndpoint(e.target.value)} /></label>}
    {provider !== "ollama" && <label>API key<input type="password" autoComplete="new-password" disabled={busy} value={key}
      placeholder={saved?.has_key && saved.provider === provider && saved.endpoint === endpoint ? "Stored securely" : "Enter provider key"}
      onChange={e => setKey(e.target.value)} /></label>}
    {provider !== "ollama" && <p className="muted">Generation can send your question and source excerpts to this provider.</p>}
    <div className="finding-actions">
      <button type="button" className="secondary" disabled={busy || !model.trim()} onClick={() => void submit(true)}>Test connection</button>
      <button disabled={busy || !model.trim()}>Save provider</button>
    </div>
    {status && <p className="notice" role="status">{status}</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
  </form>;
}
