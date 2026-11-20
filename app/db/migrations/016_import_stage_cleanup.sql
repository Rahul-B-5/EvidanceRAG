ALTER TABLE import_jobs ADD COLUMN next_stage_cleanup_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX idx_import_jobs_stage_cleanup ON import_jobs (next_stage_cleanup_at, id)
    WHERE next_stage_cleanup_at IS NOT NULL
      AND state IN ('imported','duplicate','failed') AND NOT retryable;
