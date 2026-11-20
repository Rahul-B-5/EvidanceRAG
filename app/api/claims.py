"""Search source-backed claims and record independent researcher assessments."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.db.connection import get_connection

router = APIRouter(prefix="/claims", tags=["claims"])
Scope = Annotated[int | None, Query(gt=0, le=9223372036854775807)]
ClaimID = Annotated[str, Path(pattern=r"^finding:[0-9a-f]{24}$")]
AssessmentStatus = Literal["supported", "qualified", "unsupported", "uncertain"]
FIELDS = "id, document_id, chunk_id, topic, quote, title, finding, run_id, observed_at, assessment"


class Assessment(BaseModel):
    status: AssessmentStatus
    note: str = Field(max_length=4000, pattern=r"^[^\x00]*$")
    revision: int = Field(ge=0, lt=2147483647)


def require_workspace(conn: Connection, workspace: int | None) -> None:
    if workspace is not None and not conn.execute("SELECT 1 FROM workspaces WHERE id=%s", (workspace,)).fetchone():
        raise HTTPException(404, "Workspace not found.")


def read_claim(conn: Connection, scope: int, claim_id: str) -> dict:
    row = conn.cursor(row_factory=dict_row).execute(
        f"SELECT {FIELDS} FROM visible_research_claims WHERE scope_key=%s AND id=%s", (scope, claim_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Claim source is unavailable in this scope.")
    return row


@router.get("")
def search_claims(
    workspace_id: Scope = None,
    document_id: Annotated[int | None, Query(gt=0, le=9223372036854775807)] = None,
    query: Annotated[str, Query(max_length=180)] = "",
    topic: Annotated[str, Query(max_length=40)] = "",
    status: Literal["all", "unreviewed", "supported", "qualified", "unsupported", "uncertain"] = "all",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> dict:
    with get_connection() as conn:
        require_workspace(conn, workspace_id)
        claims = conn.cursor(row_factory=dict_row).execute(f"""
            WITH terms AS (SELECT websearch_to_tsquery('english',%s) AS query)
            SELECT {FIELDS}
            FROM visible_research_claims CROSS JOIN terms
            WHERE scope_key=%s
                AND (%s::bigint IS NULL OR document_id=%s)
                AND (%s='' OR topic=%s)
                AND (%s='all' OR coalesce(assessment_status,'unreviewed')=%s)
                AND (%s='' OR search_vector @@ terms.query)
            ORDER BY ts_rank_cd(search_vector,terms.query) DESC, observed_at DESC, id
            LIMIT %s OFFSET %s
        """, (query.strip(), workspace_id or 0, document_id, document_id, topic, topic,
              status, status, query.strip(), limit + 1, offset)).fetchall()
    return {"claims": claims[:limit], "has_more": len(claims) > limit}


@router.get("/{claim_id}")
def claim_detail(claim_id: ClaimID, workspace_id: Scope = None) -> dict:
    with get_connection() as conn:
        claim = read_claim(conn, workspace_id or 0, claim_id)
        related = conn.cursor(row_factory=dict_row).execute(f"""
            SELECT {FIELDS}, shared.labels AS shared_labels
            FROM visible_research_claims
            CROSS JOIN LATERAL (
                SELECT jsonb_object_agg(item.key,item.value) AS labels
                FROM jsonb_each_text(%s::jsonb) item
                WHERE item.key IN ('subject','metric','dataset','baseline','protocol')
                  AND item.value<>'' AND lower(coalesce(finding->'relative_statement'->'conditions'->>item.key,
                                                        finding->'outcome'->>item.key))=lower(item.value)
            ) shared
            WHERE scope_key=%s AND document_id<>%s AND shared.labels IS NOT NULL
            ORDER BY (SELECT count(*) FROM jsonb_object_keys(shared.labels)) DESC, observed_at DESC, id
            LIMIT 8
        """, (Jsonb({
            **claim["finding"].get("outcome", {}),
            **(claim["finding"].get("relative_statement") or {}).get("conditions", {}),
        }), workspace_id or 0, claim["document_id"])).fetchall()
    return {**claim, "related": related}


@router.put("/{claim_id}/assessment", response_model=Assessment)
def assess_claim(claim_id: ClaimID, assessment: Assessment, workspace_id: Scope = None) -> dict:
    scope = workspace_id or 0
    with get_connection() as conn:
        claim = read_claim(conn, scope, claim_id)
        if workspace_id is not None and not conn.execute("""
            SELECT 1 FROM workspace_documents WHERE workspace_id=%s AND document_id=%s FOR KEY SHARE
        """, (workspace_id, claim["document_id"])).fetchone():
            raise HTTPException(404, "Claim source is unavailable in this scope.")
        if not conn.execute("SELECT id FROM research_claims WHERE scope_key=%s AND id=%s FOR UPDATE",
                            (scope, claim_id)).fetchone():
            raise HTTPException(404, "Claim source is unavailable in this scope.")
        cursor = conn.cursor(row_factory=dict_row)
        if assessment.revision == 0:
            row = cursor.execute("""
                INSERT INTO research_claim_assessments (scope_key,claim_id,status,note)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING status,note,revision
            """, (scope, claim_id, assessment.status, assessment.note)).fetchone()
        else:
            row = cursor.execute("""
                UPDATE research_claim_assessments SET status=%s,note=%s,revision=revision+1
                WHERE scope_key=%s AND claim_id=%s AND revision=%s RETURNING status,note,revision
            """, (assessment.status, assessment.note, scope, claim_id, assessment.revision)).fetchone()
        if row is None:
            raise HTTPException(409, "This assessment changed. Reopen the claim before editing.")
    return row
