
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT[] NOT NULL DEFAULT '{}',
    publication_year INTEGER,
    filename TEXT NOT NULL,
    file_hash CHAR(64) NOT NULL UNIQUE,
    -- Content-addressed local copy of the original PDF.  This lets a document
    -- be reprocessed even after its import location disappears.
    stored_path TEXT,
    file_size_bytes BIGINT,
    page_count INTEGER,
    processing_status TEXT NOT NULL DEFAULT 'ready',
    processing_error TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_publication_year
        CHECK (
            publication_year IS NULL
            OR publication_year BETWEEN 1000 AND 3000
        )
        ,
    CONSTRAINT valid_file_size CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    CONSTRAINT valid_page_count CHECK (page_count IS NULL OR page_count >= 0),
    CONSTRAINT valid_processing_status
        CHECK (processing_status IN ('pending', 'ready', 'failed'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,

    document_id BIGINT NOT NULL
        REFERENCES documents(id)
        ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,

    -- Do not pin the database to one embedding model's dimension.  Retrieval
    -- filters on the profile below, so vectors from distinct model spaces are
    -- never compared.
    embedding VECTOR,
    embedding_model TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,

    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', text)
    ) STORED,

    CONSTRAINT unique_document_chunk
        UNIQUE (document_id, chunk_index),

    CONSTRAINT valid_chunk_index
        CHECK (chunk_index >= 0),

    CONSTRAINT valid_page_range
        CHECK (page_start >= 1 AND page_end >= page_start),

    CONSTRAINT nonempty_chunk
        CHECK (length(trim(text)) > 0),

    CONSTRAINT valid_embedding_dimensions
        CHECK (embedding_dimensions > 0),

    CONSTRAINT embedding_matches_dimensions
        CHECK (
            embedding IS NULL
            OR vector_dims(embedding) = embedding_dimensions
        )
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id
    ON chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_search_vector
    ON chunks USING GIN(search_vector);

CREATE INDEX IF NOT EXISTS idx_documents_publication_year
    ON documents(publication_year);

CREATE INDEX IF NOT EXISTS idx_documents_processing_status
    ON documents(processing_status);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_profile
    ON chunks(embedding_model, embedding_dimensions);

CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT nonempty_conversation_title CHECK (length(trim(title)) > 0)
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_message_role CHECK (role IN ('user', 'assistant')),
    CONSTRAINT nonempty_message_content CHECK (length(trim(content)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_conversations_document_id
    ON conversations(document_id);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at
    ON messages(conversation_id, created_at, id);

CREATE TABLE IF NOT EXISTS workspaces (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT nonempty_workspace_name CHECK (length(trim(name)) > 0)
);

CREATE TABLE IF NOT EXISTS workspace_documents (
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_documents_document_id
    ON workspace_documents(document_id);

-- Scope IDs intentionally survive source deletion: a deleted source must never
-- silently expand a conversation to the entire library.
CREATE TABLE IF NOT EXISTS conversation_scopes (
    conversation_id BIGINT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    document_id BIGINT,
    workspace_id BIGINT
);
