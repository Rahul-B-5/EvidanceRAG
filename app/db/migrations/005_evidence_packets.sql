CREATE TABLE IF NOT EXISTS evidence_packets (
    id UUID PRIMARY KEY,
    workspace_id BIGINT,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
    question TEXT NOT NULL DEFAULT '' CHECK (length(question) <= 1500),
    narrative TEXT NOT NULL DEFAULT '' CHECK (length(narrative) <= 30000),
    items JSONB NOT NULL CHECK (jsonb_typeof(items) = 'array' AND jsonb_array_length(items) BETWEEN 1 AND 50),
    document_ids BIGINT[] NOT NULL CHECK (cardinality(document_ids) > 0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_packets_scope
    ON evidence_packets (workspace_id, updated_at DESC);
