import pymupdf

from app.ingestion.chunker import chunk_pages
from app.ingestion.pdf_extractor import extract_pdf


def test_captioned_table_preserves_column_relationships_on_its_page(tmp_path):
    file = tmp_path / "captioned-table.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((54, 54), "The report contains a calibration table on the next page.")
        page = pdf.new_page()
        page.insert_text((54, 65), "Table 2. Calibration results")
        for x in (54, 180, 305):
            page.draw_line((x, 76), (x, 151))
        for y in (76, 101, 126, 151):
            page.draw_line((54, y), (305, y))
        for y, metric, score in (
            (92, "Metric", "Score"), (117, "Precision", "0.84"), (142, "Recall", "0.72"),
        ):
            page.insert_text((60, y), metric)
            page.insert_text((186, y), score)
        pdf.set_toc([[1, "Introduction", 1], [1, "Results", 2]])
        pdf.save(file)

    pages = extract_pdf(file)
    assert len(pages[1]["table_rows"]) == 2
    chunks = chunk_pages(pages)
    rows = [chunk["text"] for chunk in chunks if chunk["text"].startswith("Reconstructed table row: ")]
    assert len(rows) == 2
    assert "Metric = Precision | Score = 0.84" in rows[0] and "0.72" not in rows[0]
    assert all(chunk["section_title"] == "Results" for chunk in chunks if chunk["page_start"] == 2)
    assert all(chunk["page_start"] == chunk["page_end"] == 2 for chunk in chunks if "Score =" in chunk["text"])
    assert all("Score =" not in chunk["text"] for chunk in chunks if chunk["page_start"] == 1)
