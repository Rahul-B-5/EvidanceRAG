import pymupdf

from app.ingestion.chunker import chunk_pages
from app.ingestion.pdf_extractor import extract_pdf
from evaluation.browser import hierarchical_fixture_pdf, table_fixture_pdf


def test_captioned_table_preserves_column_relationships_on_its_page(tmp_path):
    file = tmp_path / "captioned-table.pdf"
    table_fixture_pdf(file)

    pages = extract_pdf(file)
    assert len(pages[1]["table_rows"]) == 2
    chunks = chunk_pages(pages)
    rows = [chunk["text"] for chunk in chunks if chunk["text"].startswith("Reconstructed table row: ")]
    assert len(rows) == 2
    assert "Metric = Precision without tuning | Score = 0.84" in rows[0] and "0.72" not in rows[0]
    assert all(chunk["section_title"] == "Results" for chunk in chunks if chunk["page_start"] == 2)
    assert all(chunk["page_start"] == chunk["page_end"] == 2 for chunk in chunks if "Score =" in chunk["text"])
    assert all("Score =" not in chunk["text"] for chunk in chunks if chunk["page_start"] == 1)
    assert [chunk["table_row"]["cells"] for chunk in chunks if "table_row" in chunk] == [
        [{"column": "Metric", "value": "Precision without tuning"}, {"column": "Score", "value": "0.84"}],
        [{"column": "Metric", "value": "Recall"}, {"column": "Score", "value": "0.72"}],
    ]


def test_caption_below_adjacent_tables_preserves_hierarchical_metric_columns(tmp_path):
    path = tmp_path / "two-tables.pdf"
    hierarchical_fixture_pdf(path)
    rows = extract_pdf(path)[0]["table_rows"]
    assert len(rows) == 4
    for table in (1, 2):
        large = next(row for row in rows if row["caption"].startswith(f"Table {table}.")
                     and row["cells"][0]["value"] == "Large")
        assert {cell["column"]: cell["value"] for cell in large["cells"]} == {
            "System": "Large", "Development · EM": "80", "Development · F1": "81",
            "Test · EM": "82", "Test · F1": str(83 + table),
        }


def test_incomplete_header_hierarchy_does_not_assign_unlabeled_values(tmp_path):
    original = tmp_path / "complete.pdf"
    incomplete = tmp_path / "incomplete.pdf"
    hierarchical_fixture_pdf(original)
    with pymupdf.open(original) as pdf:
        page = pdf[0]
        page.add_redact_annot(pymupdf.Rect(258, 89, 278, 102))
        page.apply_redactions()
        pdf.save(incomplete)
    rows = extract_pdf(incomplete)[0].get("table_rows", [])
    assert len(rows) == 2
    assert all(row["caption"].startswith("Table 2.") for row in rows)
