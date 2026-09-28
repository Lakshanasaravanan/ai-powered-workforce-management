from pathlib import Path

from app.rag.evaluation import load_cases


def test_evidence_fixture_has_explicit_answerable_and_unanswerable_labels():
    cases = load_cases(Path(__file__).parents[1] / "data/evaluation/evidence_cases.json")
    answerable = [case for case in cases if case["label"] == "answerable"]
    unanswerable = [case for case in cases if case["label"] == "unanswerable"]
    assert len(answerable) == 5 and len(unanswerable) == 7
    assert all(case["expected_sources"] for case in answerable)
    assert all("expected_sources" not in case for case in unanswerable)
