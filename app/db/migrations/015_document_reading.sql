ALTER TABLE documents
    ADD COLUMN reading_status TEXT NOT NULL DEFAULT 'unread'
        CHECK (reading_status IN ('unread','reading','finished')),
    ADD COLUMN last_read_page INTEGER CHECK (last_read_page BETWEEN 1 AND 100000),
    ADD COLUMN last_read_at TIMESTAMPTZ,
    ADD CONSTRAINT document_reading_location CHECK ((last_read_page IS NULL) = (last_read_at IS NULL));
