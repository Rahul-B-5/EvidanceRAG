CREATE TABLE reader_bookmarks (
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL CHECK (page BETWEEN 1 AND 100000),
    PRIMARY KEY (document_id, page)
);

CREATE TABLE reader_highlights (
    id UUID PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
    page INTEGER NOT NULL CHECK (page BETWEEN 1 AND 100000),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL,
    quote TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 4000),
    revision INTEGER NOT NULL DEFAULT 1,
    CHECK (end_offset - start_offset = char_length(quote)),
    CHECK (char_length(quote) BETWEEN 1 AND 2000),
    UNIQUE (document_id, page, chunk_id, start_offset, end_offset)
);
