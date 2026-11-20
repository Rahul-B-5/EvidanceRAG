"""Reproducible graph built from persisted source-backed comparison excerpts."""

from hashlib import sha256
from collections import defaultdict
from itertools import combinations
from psycopg import Connection

from app.db.connection import get_connection
from research.contradictions import opposing_statements


def node_key(kind: str, value: str) -> str:
    return kind + ":" + sha256(value.encode()).hexdigest()[:24]


def finding_key(document_id: int, chunk_id: int, topic: str, quote: str) -> str:
    return node_key("finding", f"{document_id}:{chunk_id}:{topic}:{quote}")


def build_atlas(papers: list[dict], conn: Connection | None = None, notebook: tuple = ()) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}
    comparable = defaultdict(dict)

    def node(id_: str, kind: str, label: str, **extra) -> str:
        nodes.setdefault(id_, {"id": id_, "kind": kind, "label": label, **extra})
        return id_

    def edge(source: str, target: str, relation: str, provenance: dict, **details) -> None:
        key = (source, target, relation)
        edges[key] = {"source": source, "target": target, "relation": relation, "provenance": provenance, **details}

    def passage_node(source: dict) -> str:
        return node(f"passage:{source['chunk_id']}", "passage",
                    f"Page {source['page_start']} · Passage {source['chunk_id']}", provenance=source)

    for paper in papers:
        paper_id = paper["document_id"]
        paper_node = node(f"paper:{paper_id}", "paper", paper["title"], document_id=paper_id)
        for f in paper["findings"]:
            source = f["source"]
            if source["document_id"] != paper_id:
                continue
            claim_id = finding_key(paper_id, source["chunk_id"], f["topic"], f["quote"])
            claim = node(claim_id, "finding", f["quote"], provenance=source, outcome=f["outcome"])
            passage = passage_node(source)
            topic = node(f"topic:{f['topic']}", "topic", f["topic"])
            edge(paper_node, claim, "reports_excerpt", source)
            edge(claim, passage, "indexed_in", source)
            edge(claim, topic, "classified_as", source)
            stated = (f.get("relative_statement") or {}).get("conditions", {})
            labels = {**f["outcome"], **stated, "method": f.get("method") or stated.get("subject")}
            for field in ("dataset", "metric", "baseline", "method"):
                if value := labels.get(field):
                    entity = node(node_key(field, value.casefold()), field, value)
                    edge(claim, entity, "mentions_" + field, source)
            if labels.get("dataset") and labels.get("metric"):
                key = (labels["dataset"].casefold(), labels["metric"].casefold())
                comparable[key].setdefault(paper_id, (claim, source, labels))
    shared_edges = 0
    for group in comparable.values():
        for (left, left_source, labels), (right, right_source, _) in combinations(group.values(), 2):
            if shared_edges >= 80:
                break
            edge(left, right, "shared_dataset_metric", left_source, related_provenance=right_source,
                 shared_labels={key: labels[key] for key in ("dataset", "metric")})
            shared_edges += 1
    for kind, id_, title, document_id, chunk_id, start, end, excerpt, note in notebook:
        source = {"document_id":document_id, "chunk_id":chunk_id, "page_start":start, "page_end":end}
        paper = node(f"paper:{document_id}", "paper", title, document_id=document_id)
        artifact = node(f"{kind}:{id_}", kind, excerpt, provenance=source, note=note)
        edge(paper, artifact, "has_" + kind, source)
        edge(artifact, passage_node(source), "anchored_in", source)
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


def atlas_for_workspace(workspace_id: int | None, focus: str | None = None, *, include_notebook: bool = True) -> dict:
    with get_connection() as conn:
        rows = conn.execute("""
            WITH sampled AS (
                SELECT document_id,max(observed_at) AS latest FROM visible_research_claims
                WHERE scope_key=%s GROUP BY document_id ORDER BY latest DESC, document_id DESC LIMIT 30
            )
            SELECT s.document_id,d.title,ARRAY(
                SELECT r.finding FROM visible_research_claims r
                WHERE r.document_id=s.document_id AND r.scope_key=%s
                ORDER BY r.observed_at DESC,r.id LIMIT 20
            )
            FROM sampled s JOIN documents d ON d.id=s.document_id ORDER BY s.latest DESC,s.document_id DESC
        """, (workspace_id or 0, workspace_id or 0)).fetchall()
        papers = [{"document_id":doc, "title":title, "findings":findings} for doc, title, findings in rows]
        if focus:
            claim = conn.execute("""
                SELECT document_id,title,finding FROM visible_research_claims
                WHERE scope_key=%s AND id=%s
            """, (workspace_id or 0, focus)).fetchone()
            if claim is not None:
                document_id, title, finding = claim
                papers.insert(0, {"document_id":document_id, "title":title, "findings":[finding]})
        notebook = notebook_sources(conn, workspace_id) if include_notebook else ()
        return build_atlas(papers, conn, notebook)


def notebook_sources(conn: Connection, workspace_id: int | None) -> tuple:
    saved = conn.execute("""
        SELECT 'saved_evidence',s.chunk_id::text,d.title,c.document_id,c.id,c.page_start,c.page_end,s.passage,s.note
        FROM saved_evidence s JOIN chunks c ON c.id=s.chunk_id JOIN documents d ON d.id=c.document_id
        WHERE s.document_id=c.document_id AND s.passage=c.text
          AND s.page_start=c.page_start AND s.page_end=c.page_end
          AND (%s::bigint IS NULL OR EXISTS (
              SELECT 1 FROM workspace_documents m WHERE m.workspace_id=%s AND m.document_id=c.document_id
          ))
        ORDER BY s.saved_at DESC,s.chunk_id DESC LIMIT 50
    """, (workspace_id, workspace_id)).fetchall()
    annotations = conn.execute("""
        SELECT 'annotation',h.id::text,d.title,h.document_id,c.id,h.page,h.page,h.quote,h.note
        FROM reader_highlights h JOIN chunks c ON c.id=h.chunk_id JOIN documents d ON d.id=h.document_id
        WHERE h.document_id=c.document_id AND h.page BETWEEN c.page_start AND c.page_end
          AND substr(c.text,h.start_offset+1,h.end_offset-h.start_offset)=h.quote
          AND (%s::bigint IS NULL OR EXISTS (
              SELECT 1 FROM workspace_documents m WHERE m.workspace_id=%s AND m.document_id=h.document_id
          ))
        ORDER BY h.page,h.id LIMIT 50
    """, (workspace_id, workspace_id)).fetchall()
    return (*saved, *annotations)
