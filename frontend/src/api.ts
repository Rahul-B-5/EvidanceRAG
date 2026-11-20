const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export type Document = { id: number; title: string; filename: string; authors: string[]; page_count: number | null; chunk_count: number; processing_status: string; has_stored_source: boolean; created_at: string };
export type Passage = {chunk_id: number; page_start: number; page_end: number; text: string};
export type SavedPassage = {chunk_id: number; document_id: number; title: string; page_start: number; page_end: number; passage: string; note: string; source_exists: boolean};
export type Evidence = { evidence_id: string; chunk_id: number; document_id: number; title: string; page_start: number; page_end: number; text: string };
export type Workspace = { id: number; name: string; description: string | null; document_count: number };
export type Conversation = {id: number; title: string; document_id: number | null; workspace_id: number | null; messages: Array<{id: number; role: string; content: string; citations: Evidence[]}>};
export type Comparison = {
  fields: string[];
  papers: Array<{document_id: number; title: string; fields: Record<string, {status: string; evidence: Evidence[]}>}>;
  notice: string;
};
export type Finding = {
  topic: string; quote: string; outcome: Record<string, string>;
  source: {document_id: number; chunk_id: number; page_start: number; page_end: number; excerpt_id?: string};
};
export type StructuredComparison = {
  topics: string[];
  papers: Array<{document_id: number; title: string; findings: Finding[]; reviewed_passages: number; rejected_findings: number;
    reproducibility: Array<{item: string; mention: Finding | null}>}>;
  checks: Array<{document_ids: number[]; outcomes: Array<{
    left: Finding; right: Finding; status: "reported_difference" | "insufficient_context" | "candidate_match";
    differences: string[]; missing: string[];
  }> }>;
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
  savedEvidence: () => request<{items: SavedPassage[]}>("/saved-evidence"),
  savePassage: (id: number) => request<{chunk_id: number}>(`/saved-evidence/${id}`, {method:"PUT"}),
  updateNote: (id: number, note: string) => request<{note: string}>(`/saved-evidence/${id}`, {
    method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({note}),
  }),
  conversations: () => request<{conversations: Array<{id: number; title: string}>}>("/conversations"),
  conversation: (id: number) => request<Conversation>(`/conversations/${id}`),
  createConversation: (title: string, documentId?: number, workspaceId?: number) => request<Conversation>("/conversations", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({title, document_id:documentId, workspace_id:workspaceId})}),
  reply: (id: number, query: string) => request<unknown>("/answers", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({conversation_id:id, query})}),
  compare: (documentIds: number[], workspaceId?: number) => request<Comparison>("/comparisons", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({document_ids: documentIds, workspace_id: workspaceId})}),
  compareStructured: (documentIds: number[], workspaceId?: number) => request<StructuredComparison>("/comparisons/structured", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({document_ids: documentIds, workspace_id: workspaceId}),
  }),
  documents: () => request<{ documents: Document[] }>("/documents"),
  document: (id: number) => request<Document>(`/documents/${id}`),
  passages: (id: number, page: number, signal?: AbortSignal) => request<{passages: Passage[]}>(`/documents/${id}/passages?page=${page}`, {signal}),
  upload: (file: File) => { const data = new FormData(); data.append("file", file); return request<{ document_id: number; status: string }>("/documents", { method: "POST", body: data }); },
  remove: (id: number) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  search: (query: string, documentId?: number, workspaceId?: number) => request<{ evidence: Evidence[]; evidence_count: number }>(`/search?${new URLSearchParams({ query, ...(documentId ? { document_id: String(documentId) } : {}), ...(workspaceId ? {workspace_id: String(workspaceId)} : {}) })}`),
  answer: (query: string, documentId?: number) => request<{ answer: string; abstained: boolean; reason: string | null; citations: Evidence[]; evidence: Evidence[] }>("/answers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, document_id: documentId }) }),
  workspaces: () => request<{ workspaces: Workspace[] }>("/workspaces"),
  workspace: (id: number) => request<Workspace & {documents: Array<{id: number}>}>(`/workspaces/${id}`),
  membership: (workspaceId: number, documentId: number, add: boolean) => request<unknown>(`/workspaces/${workspaceId}/documents/${documentId}`, {method: add ? "PUT" : "DELETE"}),
  createWorkspace: (name: string, description: string) => request<Workspace>("/workspaces", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }) }),
  sourceUrl: (id: number) => `${API_BASE}/documents/${id}/source`,
};
