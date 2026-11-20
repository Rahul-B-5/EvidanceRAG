"""Find papers that share reported dataset and metric labels with the current source."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from psycopg.rows import dict_row

from app.db.connection import get_connection

router = APIRouter(prefix="/documents")


@router.get("/{document_id}/related-papers")
def related_papers(
    document_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    workspace_id: Annotated[int | None, Query(gt=0, le=9223372036854775807)] = None,
) -> dict:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        if cursor.execute("""
            SELECT id FROM documents WHERE id=%s AND (
                %s::bigint IS NULL OR EXISTS (
                    SELECT 1 FROM workspace_documents m WHERE m.workspace_id=%s AND m.document_id=documents.id
                )
            )
        """, (document_id, workspace_id, workspace_id)).fetchone() is None:
            raise HTTPException(404, "Paper is unavailable in this scope.")
        rows = cursor.execute("""
            WITH origin AS MATERIALIZED (
                SELECT id, scope_key, observed_at, finding->'source' AS source,
                       finding->'outcome'->>'dataset' AS dataset, finding->'outcome'->>'metric' AS metric
                FROM visible_research_claims
                WHERE scope_key=%s AND document_id=%s AND topic='results'
                  AND nullif(finding->'outcome'->>'dataset','') IS NOT NULL
                  AND nullif(finding->'outcome'->>'metric','') IS NOT NULL
                ORDER BY observed_at DESC,id LIMIT 40
            ), matched AS (
                SELECT DISTINCT ON (candidate.document_id)
                    candidate.document_id, candidate.title, candidate.id AS claim_id,
                    candidate.finding->'source' AS source, candidate.observed_at,
                    origin.id AS origin_claim_id, origin.source AS origin_source, origin.dataset, origin.metric
                FROM origin
                JOIN visible_research_claims candidate ON candidate.scope_key=origin.scope_key
                    AND candidate.document_id<>%s AND candidate.topic='results'
                    AND lower(candidate.finding->'outcome'->>'dataset')=lower(origin.dataset)
                    AND lower(candidate.finding->'outcome'->>'metric')=lower(origin.metric)
                ORDER BY candidate.document_id,candidate.observed_at DESC,origin.observed_at DESC,candidate.id,origin.id
            )
            SELECT document_id,title,claim_id,source,origin_claim_id,origin_source,dataset,metric
            FROM matched ORDER BY observed_at DESC,document_id LIMIT 8
        """, (workspace_id or 0, document_id, document_id)).fetchall()
    return {"papers": rows}
