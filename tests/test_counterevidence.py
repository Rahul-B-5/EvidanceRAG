from research.counterevidence import focus_terms, rank_passages


def test_ranks_matching_cross_paper_qualifications_and_preserves_source():
    claim = {"label": "F1 improved on Orchard under limited labels.",
             "outcome": {"metric": "F1", "dataset": "Orchard"}, "provenance": {"document_id": 1}}
    rows = [
        (10, 1, "Original paper", 1, 1, "F1 did not improve on Orchard.", 1.0),
        (11, 2, "Reference", 3, 3, "Orchard and F1 are in the protocol.", 0.9),
        (12, 3, "Candidate", 6, 7, "We found no significant improvement in F1 on Orchard.", 0.2),
        (13, 4, "Unrelated topic", 1, 1, "The trial did not generalize.", 1.0),
    ]
    result = rank_passages(rows, claim, focus_terms(claim))
    assert [p["chunk_id"] for p in result] == [12, 11]
    assert result[0]["signal"] == "no significant improvement"
    assert result[0]["condition_labels"] == {"metric": "F1", "dataset": "Orchard"}
    assert result[0]["page_start"] == 6


def test_qualifier_far_from_matching_terms_is_not_a_challenge_signal():
    claim = {"label": "Orchard defect detection", "provenance": {"document_id": 1}}
    text = "The trial did not improve results. " + ("Unrelated methods. " * 30) + " The Orchard benchmark is part of the evaluation."
    result = rank_passages([(11, 2, "Other paper", 3, 4, text, 0.9)], claim, ["orchard"])
    assert result[0]["signal"] is None
