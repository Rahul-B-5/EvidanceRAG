const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export type DocumentMetadata = {title: string; authors: string[]; publication_year: number | null;
  doi: string | null; venue: string | null; tags: string[]; metadata_revision: number};
export type Document = DocumentMetadata & {id: number; filename: string; page_count: number | null;
  chunk_count: number; processing_status: string; has_stored_source: boolean; created_at: string};
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
export type ComparisonRun = {
  id: string; workspace_id: number | null; document_ids: number[]; titles: string[];
  created_at: string; status: "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
  error: string | null;
};
export type Provenance = Finding["source"];
export type AtlasNode = {id: string; kind: string; label: string; document_id?: number; provenance?: Provenance};
export type Atlas = {nodes: AtlasNode[]; edges: Array<{source: string; target: string; relation: string; provenance: Provenance}>};
export type CandidatePassage = Provenance & {title: string; excerpt: string; signal: string | null; matched_terms: string[]; condition_labels: Record<string,string>};
export type ClaimReview = {
  candidate_chunk_id: number;
  candidate_snapshot: CandidatePassage;
  relation: "supports" | "qualifies" | "challenges" | "uncertain";
  alignment: "aligned" | "different" | "unknown";
  note: string;
};
export type Counterevidence = {
  finding: AtlasNode;
  passages: CandidatePassage[];
  reviews: ClaimReview[];
};
export type ReproductionDossier = {
  document_id: number;
  title: string;
  items: Array<{label: string; verify: string; status: "specific_detail" | "mention" | "not_located";
    matched_text: string | null; excerpt: string | null; source: Provenance | null}>;
};
export type CoverageMap = {
  question: string; anchors: string[];
  facets: Array<{title: string; question: string; status: "multiple_papers" | "single_paper" | "not_located";
    passages: Array<Provenance & {title: string; excerpt: string}>}>;
};
export type InvestigationPlan = {question: string; hypothesis: string; baseline: string; metrics: string; validation: string};
export type ResearchDirections = {
  reviewed_paper_count: number;
  directions: Array<{id: string; title: string; paper_count: number; verification: string; plan: InvestigationPlan;
    evidence: Array<Provenance & {title: string; excerpt: string; signal: string}>}>;
};
export type PacketSummary = {id: string; title: string; revision: number; updated_at: string; item_count: number};
export type EvidencePacket = {
  id: string; title: string; question: string; narrative: string; revision: number; workspace_id: number | null;
  items: Array<Omit<SavedPassage, "source_exists"> & {authors: string[]; publication_year: number | null;
    saved_at: string; doi?: string | null; venue?: string | null}>;
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
  comparisonRuns: (workspaceId?: number) => request<{runs: ComparisonRun[]}>(workspaceId ? `/comparison-runs?workspace_id=${workspaceId}` : "/comparison-runs"),
  startComparison: (documentIds: number[], workspaceId?: number) => request<ComparisonRun>("/comparison-runs", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({document_ids: documentIds, workspace_id: workspaceId}),
  }),
  comparisonRun: (id: string, signal?: AbortSignal) => request<ComparisonRun & {result: StructuredComparison}>(`/comparison-runs/${id}`, {signal}),
  cancelComparison: (id: string) => request<void>(`/comparison-runs/${id}/cancel`, {method:"POST"}),
  atlas: (workspaceId: string, signal?: AbortSignal) => request<Atlas>(workspaceId ? `/evidence-atlas?workspace_id=${workspaceId}` : "/evidence-atlas", {signal}),
  counterevidence: (id: string, workspaceId: string, signal?: AbortSignal) => request<Counterevidence>(
    `/evidence-atlas/${encodeURIComponent(id)}/counterevidence${workspaceId ? `?workspace_id=${workspaceId}` : ""}`, {signal}),
  saveClaimReview: (id: string, chunk: number, workspaceId: string, review: Pick<ClaimReview, "relation" | "alignment" | "note">) => request<ClaimReview>(
    `/evidence-atlas/${encodeURIComponent(id)}/reviews/${chunk}${workspaceId ? `?workspace_id=${workspaceId}` : ""}`, {
      method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(review),
    }),
  documents: () => request<{ documents: Document[] }>("/documents"),
  document: (id: number) => request<Document>(`/documents/${id}`),
  editDocument: (id: number, metadata: DocumentMetadata) => request<Document>(`/documents/${id}/metadata`, {
    method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify(metadata),
  }),
  passages: (id: number, page: number, signal?: AbortSignal) => request<{passages: Passage[]}>(`/documents/${id}/passages?page=${page}`, {signal}),
  reproduction: (id: string, workspaceId: string, signal?: AbortSignal) => request<ReproductionDossier>(
    `/documents/${id}/reproducibility${workspaceId ? `?workspace_id=${workspaceId}` : ""}`, {signal}),
  coverage: (question: string, workspaceId: string, useProvider: boolean, signal?: AbortSignal) => request<CoverageMap>("/research/coverage", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({question, workspace_id:workspaceId ? Number(workspaceId) : undefined, use_provider:useProvider}), signal,
  }),
  directions: (workspaceId: string, signal?: AbortSignal) => request<ResearchDirections>(
    workspaceId ? `/research/directions?workspace_id=${workspaceId}` : "/research/directions", {signal}),
  packets: (workspaceId: string) => request<{packets: PacketSummary[]}>(
    workspaceId ? `/evidence-packets?workspace_id=${workspaceId}` : "/evidence-packets"),
  createPacket: (workspaceId: string, title: string, chunkIds: number[]) => request<EvidencePacket>("/evidence-packets", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({workspace_id:workspaceId ? Number(workspaceId) : undefined, title, chunk_ids:chunkIds}),
  }),
  packet: (id: string) => request<EvidencePacket>(`/evidence-packets/${id}`),
  editPacket: (id: string, fields: Pick<EvidencePacket, "title" | "question" | "narrative" | "revision">) => request<EvidencePacket>(
    `/evidence-packets/${id}`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify(fields)}),
  draftPacket: (id: string) => request<{answer: string; abstained: boolean; reason: string | null}>(
    `/evidence-packets/${id}/draft`, {method:"POST"}),
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
