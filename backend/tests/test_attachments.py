"""Choosing which part of an attached file goes to the model."""

from app.ai import attachments


DOC = (
    "--- Page 1 ---\nInspection report for Kalinga Opencast Project, 12 September.\n\n"
    "Haul road berm on the east bench was below half the wheel height of the largest dumper.\n\n"
    "--- Page 2 ---\nPM10 at the core zone station measured 164 micrograms per cubic metre.\n\n"
    "Recommendation: raise the berm to at least half wheel height within 24 hours.\n\n"
    + "Unrelated appendix text. " * 200
)


def test_excerpt_prefers_matching_passages():
    ex = attachments.excerpt("What did the report say about PM10?", DOC)
    assert "164" in ex and len(ex) <= attachments.EXCERPT_BUDGET + 10


def test_excerpt_for_summary_starts_at_the_beginning():
    ex = attachments.excerpt("Summarise this document", DOC)
    assert ex.startswith("--- Page 1 ---") and len(ex) <= attachments.EXCERPT_BUDGET + 10


def test_excerpt_without_matches_falls_back_to_the_start():
    ex = attachments.excerpt("zzzz qqqq", DOC)
    assert "Kalinga" in ex


def test_clean_collapses_whitespace():
    assert attachments.clean("a   b\n\n\n\nc") == "a b\n\nc"
