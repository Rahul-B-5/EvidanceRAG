from app.ingestion.chunker import chunk_pages
from app.ingestion.pdf_extractor import extract_pdf
from evaluation.browser import table_fixture_pdf


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
