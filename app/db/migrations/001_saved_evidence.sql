CREATE TABLE IF NOT EXISTS saved_evidence (
    chunk_id BIGINT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    passage TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
