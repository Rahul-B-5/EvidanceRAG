const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export type Document = { id: number; title: string; filename: string; authors: string[]; page_count: number | null; chunk_count: number; processing_status: string; has_stored_source: boolean; created_at: string };
export type Evidence = { evidence_id: string; chunk_id: number; document_id: number; title: string; page_start: number; page_end: number; text: string };
export type Workspace = { id: number; name: string; description: string | null; document_count: number };
export type Comparison = {
  fields: string[];
  papers: Array<{document_id: number; title: string; fields: Record<string, {status: string; evidence: Evidence[]}>}>;
  notice: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((e: {msg: string}) => e.msg).join("; ") : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  compare: (documentIds: number[]) => request<Comparison>("/comparisons", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({document_ids: documentIds})}),
  documents: () => request<{ documents: Document[] }>("/documents"),
  document: (id: number) => request<Document>(`/documents/${id}`),
  upload: (file: File) => { const data = new FormData(); data.append("file", file); return request<{ document_id: number; status: string }>("/documents", { method: "POST", body: data }); },
  remove: (id: number) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  search: (query: string, documentId?: number) => request<{ evidence: Evidence[]; evidence_count: number }>(`/search?${new URLSearchParams({ query, ...(documentId ? { document_id: String(documentId) } : {}) })}`),
  answer: (query: string, documentId?: number) => request<{ answer: string; abstained: boolean; reason: string | null; citations: Evidence[]; evidence: Evidence[] }>("/answers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, document_id: documentId }) }),
  workspaces: () => request<{ workspaces: Workspace[] }>("/workspaces"),
  createWorkspace: (name: string, description: string) => request<Workspace>("/workspaces", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }) }),
  sourceUrl: (id: number) => `${API_BASE}/documents/${id}/source`,
};
