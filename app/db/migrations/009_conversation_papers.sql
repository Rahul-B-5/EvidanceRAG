ALTER TABLE conversation_scopes ADD COLUMN document_ids BIGINT[];

ALTER TABLE conversation_scopes ADD CONSTRAINT valid_conversation_papers CHECK (
    document_ids IS NULL OR (
        document_id IS NULL
        AND cardinality(document_ids) BETWEEN 1 AND 12
        AND array_position(document_ids, NULL) IS NULL
        AND 0 < ALL(document_ids)
    )
);

INSERT INTO conversation_scopes (conversation_id, document_id)
SELECT id, document_id FROM conversations WHERE document_id IS NOT NULL
ON CONFLICT (conversation_id) DO NOTHING;
