ALTER TABLE evidence_packets ADD COLUMN template TEXT NOT NULL DEFAULT 'general';

ALTER TABLE evidence_packets ADD CONSTRAINT valid_evidence_packet_template CHECK (
    template IN ('general', 'literature-review', 'technical-comparison', 'methodology',
                 'research-gap', 'reproduction', 'question-investigation')
);
