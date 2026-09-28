"""eval_curator_groundedness.py: Evaluates Curator agent grounding faithfulness and schema validation."""

import pytest
from pydantic import ValidationError

from src.agents.curator import (
    DistilledRule,
    verify_groundedness,
)
from configs.settings import CACHE_DIR, GROUNDEDNESS_THRESHOLD

SAMPLE_GROUND_TRUTH_STATUTE = """
A decision is solely automated if there is no meaningful human involvement in the taking of the decision.
The controller must ensure that suitable measures are in place to safeguard the data subject's rights,
freedoms and legitimate interests, at least the right to obtain human intervention on the part of the
controller, to express his or her point of view and to contest the decision.
"""


def test_eval_groundedness_faithful_citation():
    """Verify that an authentic quotation achieves an overlap ratio >= 0.85."""
    rule = DistilledRule(
        rule_id="uk_duaa_human_intervention",
        statute_reference="DUAA 2025 c. 18 s. 80 (Art 22C)",
        jurisdiction="UK",
        verbatim_quote="A decision is solely automated if there is no meaningful human involvement in the taking of the decision.",
        enforceable_constraint="Require HumanInterventionHook in solely automated decision flows.",
        trigger_domain="general_adm",
    )
    passes = verify_groundedness(
        rule=rule,
        raw_source_text=SAMPLE_GROUND_TRUTH_STATUTE,
        match_threshold=0.85,
    )
    assert passes is True


def test_eval_groundedness_rejects_hallucinated_legal_text():
    """Verify that fabricated or heavily distorted legal assertions fail the groundedness gate."""
    hallucinated_rule = DistilledRule(
        rule_id="fake_hallucinated_rule",
        statute_reference="DUAA 2025 c. 18 s. 80",
        jurisdiction="UK",
        verbatim_quote="All algorithms must be immediately deleted if an employee objects to automated screening.",
        enforceable_constraint="Block all automated models immediately.",
        trigger_domain="employment_screening",
    )
    passes = verify_groundedness(
        rule=hallucinated_rule,
        raw_source_text=SAMPLE_GROUND_TRUTH_STATUTE,
        match_threshold=0.85,
    )
    assert passes is False


def test_eval_distilled_rule_schema_completeness():
    """Verify that valid statutory extractions adhere to schema invariants."""
    rule = DistilledRule(
        rule_id="uk_duaa_s80_meaningful_human",
        statute_reference="DUAA 2025 c. 18 s. 80 (Art 22C)",
        jurisdiction="UK",
        verbatim_quote="A decision is solely automated if there is no meaningful human involvement in the taking of the decision.",
        enforceable_constraint="Require HumanInterventionHook in solely automated decision flows.",
        trigger_domain="general_adm",
        status="ACTIVE",
    )
    assert rule.rule_id == "uk_duaa_s80_meaningful_human"
    assert rule.status == "ACTIVE"


def test_eval_distilled_rule_schema_rejects_invalid_domain():
    """Verify Pydantic validation error when an unapproved trigger domain is used."""
    with pytest.raises(ValidationError):
        DistilledRule(
            rule_id="invalid_domain_rule",
            statute_reference="DUAA 2025 s. 80",
            jurisdiction="UK",
            verbatim_quote="A decision is solely automated if there is no meaningful human involvement.",
            enforceable_constraint="Some technical constraint",
            trigger_domain="invalid_nonexistent_domain",  # Fails Literal validation
        )