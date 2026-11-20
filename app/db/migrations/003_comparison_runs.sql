CREATE TABLE IF NOT EXISTS comparison_runs (
    id UUID PRIMARY KEY,
    workspace_id BIGINT,
    document_ids BIGINT[] NOT NULL CHECK (cardinality(document_ids) BETWEEN 2 AND 6),
    titles TEXT[] NOT NULL,
    papers JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_until TIMESTAMPTZ NOT NULL,
    error TEXT,
    CHECK (cardinality(document_ids) = cardinality(titles))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_comparison_one_active_run
    ON comparison_runs ((true)) WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_comparison_run_history
    ON comparison_runs (workspace_id, created_at DESC);
