CREATE TABLE IF NOT EXISTS collections (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_scope_name
    ON collections (COALESCE(workspace_id, 0), LOWER(name));

CREATE TABLE IF NOT EXISTS collection_documents (
    collection_id BIGINT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(collection_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_collection_documents_document
    ON collection_documents(document_id);
