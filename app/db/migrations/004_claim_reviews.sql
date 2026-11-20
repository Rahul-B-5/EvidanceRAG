CREATE TABLE IF NOT EXISTS claim_reviews (
    scope_key BIGINT NOT NULL CHECK (scope_key >= 0),
    finding_id TEXT NOT NULL,
    candidate_chunk_id BIGINT NOT NULL,
    candidate_document_id BIGINT NOT NULL,
    relation TEXT NOT NULL CHECK (relation IN ('supports','qualifies','challenges','uncertain')),
    alignment TEXT NOT NULL CHECK (alignment IN ('aligned','different','unknown')),
    note TEXT NOT NULL CHECK (length(note) <= 4000),
    finding_snapshot JSONB NOT NULL,
    candidate_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scope_key, finding_id, candidate_chunk_id)
);
