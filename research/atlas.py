"""Reproducible graph built from persisted source-backed comparison excerpts."""

from hashlib import sha256
from psycopg import Connection

from app.db.connection import get_connection
from research.contradictions import opposing_statements


def node_key(kind: str, value: str) -> str:
    return kind + ":" + sha256(value.encode()).hexdigest()[:24]


def finding_key(document_id: int, chunk_id: int, topic: str, quote: str) -> str:
    return node_key("finding", f"{document_id}:{chunk_id}:{topic}:{quote}")


def build_atlas(papers: list[dict], conn: Connection | None = None) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}

    def node(id_: str, kind: str, label: str, **extra) -> str:
        nodes.setdefault(id_, {"id": id_, "kind": kind, "label": label, **extra})
        return id_

    def edge(source: str, target: str, relation: str, provenance: dict) -> None:
        key = (source, target, relation)
        edges[key] = {"source": source, "target": target, "relation": relation, "provenance": provenance}

    for paper in papers:
        paper_id = paper["document_id"]
        paper_node = node(f"paper:{paper_id}", "paper", paper["title"], document_id=paper_id)
        for f in paper["findings"]:
            source = f["source"]
            if source["document_id"] != paper_id:
                continue
            claim_id = finding_key(paper_id, source["chunk_id"], f["topic"], f["quote"])
            claim = node(claim_id, "finding", f["quote"], provenance=source, outcome=f["outcome"])
            passage = node(f"passage:{source['chunk_id']}", "passage",
                           f"Page {source['page_start']} · Passage {source['chunk_id']}", provenance=source)
            topic = node(f"topic:{f['topic']}", "topic", f["topic"])
            edge(paper_node, claim, "reports_excerpt", source)
            edge(claim, passage, "indexed_in", source)
            edge(claim, topic, "classified_as", source)
            for field in ("dataset", "metric", "baseline"):
                if value := f["outcome"].get(field):
                    entity = node(node_key(field, value.casefold()), field, value)
                    edge(claim, entity, "mentions_" + field, source)
    contradictions = opposing_statements(papers, conn)
    for pair in contradictions:
        for side in ("left", "right"):
            item = pair[side]
            source = item["source"]
            item["finding_id"] = finding_key(source["document_id"], source["chunk_id"], "results", item["finding_quote"])
        left, right = pair["left"], pair["right"]
        edge(left["finding_id"], right["finding_id"], "potential_disagreement", left["source"])
        edges[(left["finding_id"], right["finding_id"], "potential_disagreement")]["related_provenance"] = right["source"]
    return {"nodes": list(nodes.values()), "edges": list(edges.values()), "contradictions": contradictions}


def atlas_for_workspace(workspace_id: int | None) -> dict:
    with get_connection() as conn:
        rows = conn.execute("""
            WITH latest_runs AS (
                SELECT workspace_id, papers, updated_at
                FROM comparison_runs
                WHERE workspace_id IS NOT DISTINCT FROM %s::bigint AND papers <> '[]'::jsonb
                ORDER BY updated_at DESC, id DESC LIMIT 50
            ), paper_extracts AS (
                SELECT DISTINCT ON (d.id) d.id, p.paper, r.updated_at
                FROM latest_runs r CROSS JOIN LATERAL jsonb_array_elements(r.papers) p(paper)
                JOIN documents d ON d.id=(p.paper->>'document_id')::bigint
                WHERE r.workspace_id IS NULL OR EXISTS (
                    SELECT 1 FROM workspace_documents m
                    WHERE m.workspace_id=r.workspace_id AND m.document_id=d.id
                )
                ORDER BY d.id, r.updated_at DESC
            )
            SELECT paper FROM paper_extracts ORDER BY updated_at DESC, id DESC LIMIT 30
        """, (workspace_id,)).fetchall()
        return build_atlas([r[0] for r in rows], conn)
