from app.ingestion.chunker import chunk_pages


def test_chunks_on_distinct_physical_pages_never_share_text():
    chunks = chunk_pages([
        {"page_number": 7, "text": "Third heading"},
        {"page_number": 1, "text": "Opening paragraph"},
        {"page_number": 4, "text": " \n "},
    ], chunk_size=120, chunk_overlap=30)
    assert chunks == [
        {"chunk_index": 0, "text": "Opening paragraph", "page_start": 1, "page_end": 1},
        {"chunk_index": 1, "text": "Third heading", "page_start": 7, "page_end": 7},
    ]


def test_word_overlap_and_long_tokens_make_progress():
    chunks = chunk_pages([
        {"page_number": 2, "text": "alpha beta\ngamma delta epsilon"},
        {"page_number": 3, "text": "abcdefghijklmno"},
    ], chunk_size=13, chunk_overlap=6)
    assert [item["text"] for item in chunks] == [
        "alpha beta", "beta\ngamma", "gamma delta", "delta epsilon", "abcdefghijklm", "no",
    ]
    assert [item["page_end"] for item in chunks] == [2, 2, 2, 2, 3, 3]
