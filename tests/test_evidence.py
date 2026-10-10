import pytest
from app.reports import assess_claim
from app.schemas import PreferenceInput, WatchInput

SOURCES = {
    "primary": {
        "source_type": "sec",
        "excerpt": "Revenue was USD 10 billion in FY2025.",
        "url": "https://www.sec.gov/a",
        "content_hash": "a",
    },
    "secondary": {
        "source_type": "web",
        "excerpt": "Revenue was USD 9 billion in FY2025.",
        "url": "https://example.com/b",
        "content_hash": "b",
    },
    "social": {
        "source_type": "x",
        "excerpt": "Revenue will double next year.",
        "url": "https://x.com/i/status/1",
        "content_hash": "c",
    },
}


def claim(kind="fact", assessment="supported", evidence=None):
    return {
        "text": "Revenue was 10 billion",
        "kind": kind,
        "assessment": assessment,
        "evidence": evidence or [],
    }


def evidence(source="primary", stance="support", quote="Revenue was USD 10 billion in FY2025."):
    return {"source_id": source, "stance": stance, "quote": quote, "rationale": "period matched"}


def test_support_is_grounded_but_not_probability():
    result = assess_claim(claim(evidence=[evidence()]), SOURCES)
    assert result["status"] == "supported"
    assert result["evidence_strength"]["primary_sources"] == 1
    assert result["evidence_strength"]["calibrated_probability"] is False


@pytest.mark.parametrize("kind", ["prediction", "opinion"])
def test_predictions_and_opinions_cannot_be_verified(kind):
    assert assess_claim(claim(kind=kind, evidence=[evidence()]), SOURCES)["status"] == "not_verifiable"


def test_both_directions_expose_conflict():
    rows = [evidence(), evidence("secondary", "contradict", "Revenue was USD 9 billion in FY2025.")]
    assert assess_claim(claim(evidence=rows), SOURCES)["status"] == "conflicting"


def test_fake_ids_and_made_up_quotes_are_removed():
    result = assess_claim(
        claim(evidence=[evidence("invented"), evidence(quote="Revenue was 200 billion")]), SOURCES
    )
    assert result["status"] == "insufficient_evidence"
    assert result["evidence"] == []
    assert len(result["validation_warnings"]) == 2


def test_social_post_cannot_verify_its_own_claim():
    result = assess_claim(
        claim(evidence=[evidence("social", quote="Revenue will double next year.")]), SOURCES
    )
    assert result["status"] == "insufficient_evidence"


def test_same_evidence_is_not_counted_twice():
    result = assess_claim(claim(evidence=[evidence(), evidence()]), SOURCES)
    assert len(result["evidence"]) == 1


def test_inference_remains_distinct_from_fact():
    assert (
        assess_claim(claim(kind="inference", evidence=[evidence()]), SOURCES)["status"]
        == "partially_supported"
    )


def test_ticker_and_preferences_validate():
    assert WatchInput(ticker="$nvda").ticker == "NVDA"
    with pytest.raises(ValueError):
        WatchInput(ticker="NVDA; DROP TABLE watchlist")
    with pytest.raises(ValueError):
        PreferenceInput(risk_tolerance="certain_profit", investment_horizon="forever")
