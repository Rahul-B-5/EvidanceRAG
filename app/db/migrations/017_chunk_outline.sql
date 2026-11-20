ALTER TABLE chunks ADD COLUMN section_title TEXT
    CHECK (section_title IS NULL OR char_length(section_title) BETWEEN 1 AND 240);
