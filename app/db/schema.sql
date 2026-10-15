
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT[] NOT NULL DEFAULT '{}',
    publication_year INTEGER,
    filename TEXT NOT NULL,
    file_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_publication_year
        CHECK (
            publication_year IS NULL
            OR publication_year BETWEEN 1000 AND 3000
        )
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

    embedding VECTOR(384),

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
        CHECK (length(trim(text)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id
    ON chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_search_vector
    ON chunks USING GIN(search_vector);

CREATE INDEX IF NOT EXISTS idx_documents_publication_year
    ON documents(publication_year);
