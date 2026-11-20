CREATE TABLE research_claims (
    scope_key BIGINT NOT NULL CHECK (scope_key >= 0),
    id TEXT NOT NULL CHECK (id ~ '^finding:[0-9a-f]{24}$'),
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    quote TEXT NOT NULL CHECK (length(quote) BETWEEN 12 AND 650),
    finding JSONB NOT NULL,
    run_id UUID NOT NULL REFERENCES comparison_runs(id),
    observed_at TIMESTAMPTZ NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', quote || ' ' || topic || ' ' || coalesce(finding->>'outcome', ''))
    ) STORED,
    PRIMARY KEY (scope_key, id)
);

CREATE INDEX idx_research_claim_search ON research_claims USING GIN (search_vector);
CREATE INDEX idx_research_claim_scope_paper ON research_claims(scope_key, document_id, topic);
CREATE INDEX idx_research_claim_chunk ON research_claims(chunk_id);

CREATE TABLE research_claim_assessments (
    scope_key BIGINT NOT NULL,
    claim_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('supported', 'qualified', 'unsupported', 'uncertain')),
    note TEXT NOT NULL CHECK (length(note) <= 4000),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    PRIMARY KEY (scope_key, claim_id),
    FOREIGN KEY (scope_key, claim_id) REFERENCES research_claims(scope_key, id) ON DELETE CASCADE
);

CREATE FUNCTION record_comparison_claims(run UUID, workspace BIGINT, paper JSONB, observed TIMESTAMPTZ)
RETURNS void LANGUAGE SQL AS $$
    INSERT INTO research_claims (scope_key,id,document_id,chunk_id,topic,quote,finding,run_id,observed_at)
    SELECT DISTINCT ON (identity.id)
        COALESCE(workspace,0), identity.id, c.document_id, c.id, f->>'topic', f->>'quote', f, run, observed
    FROM jsonb_array_elements(paper->'findings') WITH ORDINALITY AS findings(f, sequence)
    JOIN chunks c ON c.id=(f->'source'->>'chunk_id')::bigint
    CROSS JOIN LATERAL (
        SELECT 'finding:' || left(encode(sha256(convert_to(concat_ws(':',
            c.document_id, c.id, f->>'topic', f->>'quote'), 'UTF8')), 'hex'),24) AS id
    ) identity
    WHERE c.document_id=(paper->>'document_id')::bigint
      AND c.document_id=(f->'source'->>'document_id')::bigint
      AND c.page_start=(f->'source'->>'page_start')::int AND c.page_end=(f->'source'->>'page_end')::int
      AND length(f->>'quote') BETWEEN 12 AND 650
      AND strpos(trim(regexp_replace(c.text, '[[:space:]]+', ' ', 'g')), f->>'quote') > 0
      AND (workspace IS NULL OR EXISTS (
          SELECT 1 FROM workspace_documents m WHERE m.workspace_id=workspace AND m.document_id=c.document_id
      ))
    ORDER BY identity.id, sequence
    ON CONFLICT (scope_key,id) DO UPDATE SET finding=EXCLUDED.finding,run_id=EXCLUDED.run_id,observed_at=EXCLUDED.observed_at
    WHERE research_claims.observed_at<=EXCLUDED.observed_at;
$$;

SELECT record_comparison_claims(r.id,r.workspace_id,p.paper,r.updated_at)
FROM comparison_runs r CROSS JOIN LATERAL jsonb_array_elements(r.papers) p(paper);

CREATE VIEW visible_research_claims AS
SELECT r.*, d.title, a.status AS assessment_status,
       CASE WHEN a.claim_id IS NOT NULL THEN jsonb_build_object(
           'status',a.status,'note',a.note,'revision',a.revision
       ) END AS assessment
FROM research_claims r JOIN documents d ON d.id=r.document_id JOIN chunks c ON c.id=r.chunk_id
LEFT JOIN research_claim_assessments a ON a.scope_key=r.scope_key AND a.claim_id=r.id
WHERE c.document_id=r.document_id
  AND c.page_start=(r.finding->'source'->>'page_start')::int AND c.page_end=(r.finding->'source'->>'page_end')::int
  AND strpos(trim(regexp_replace(c.text, '[[:space:]]+', ' ', 'g')), r.quote)>0
  AND (r.scope_key=0 OR EXISTS (
      SELECT 1 FROM workspace_documents m WHERE m.workspace_id=r.scope_key AND m.document_id=r.document_id
  ));
