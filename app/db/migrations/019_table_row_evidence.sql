ALTER TABLE chunks ADD COLUMN table_row JSONB
    CHECK (table_row IS NULL OR (
        page_start = page_end AND
        jsonb_typeof(table_row) = 'object' AND
        table_row ?& ARRAY['caption','group','cells'] AND
        jsonb_typeof(table_row->'caption') = 'string' AND
        jsonb_typeof(table_row->'group') = 'string' AND
        jsonb_typeof(table_row->'cells') = 'array'
    ));
