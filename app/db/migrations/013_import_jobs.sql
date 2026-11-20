CREATE TABLE import_jobs (
    id UUID PRIMARY KEY,
    filename TEXT NOT NULL CHECK (length(filename) BETWEEN 1 AND 240),
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued','indexing','imported','duplicate','failed')),
    document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,
    error TEXT,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    interruptions INTEGER NOT NULL DEFAULT 0 CHECK (interruptions BETWEEN 0 AND 3),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_import_jobs_pending ON import_jobs(created_at,id) WHERE state IN ('queued','indexing');
CREATE INDEX idx_import_jobs_document ON import_jobs(document_id);
