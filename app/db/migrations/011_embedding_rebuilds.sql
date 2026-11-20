CREATE TABLE embedding_rebuilds (
    id UUID PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    total_chunks INTEGER NOT NULL CHECK (total_chunks > 0),
    prepared_chunks INTEGER NOT NULL DEFAULT 0 CHECK (prepared_chunks BETWEEN 0 AND total_chunks),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'interrupted', 'cancelled')),
    error TEXT,
    lease_until TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_embedding_one_active_rebuild
    ON embedding_rebuilds (document_id) WHERE status IN ('queued', 'running');
CREATE INDEX idx_embedding_rebuild_document_history ON embedding_rebuilds (document_id, created_at DESC);
