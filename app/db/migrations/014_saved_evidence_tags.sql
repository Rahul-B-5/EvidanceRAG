ALTER TABLE saved_evidence ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}'
    CHECK (cardinality(tags) <= 12 AND array_position(tags, NULL) IS NULL);
