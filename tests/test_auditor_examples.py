"""tests/test_auditor_examples.py: Integration tests validating Auditor against PR fixtures."""

from pathlib import Path
import pytest
from configs.settings import PROJECT_ROOT
from src.agents.auditor import audit_file

EXAMPLES_DIR = PROJECT_ROOT / "examples"


def test_compliant_pipeline_passes():
    """Asserts that clean pipeline code passes without blocking violations."""
    fixture = EXAMPLES_DIR / "pr_compliant_pipeline.py"
    report = audit_file(fixture)

    assert report.status == "PASSED", f"Compliant PR falsely blocked: {report.violations}"
    assert report.blocking_violations == 0


def test_deceptive_prompt_violation_fails():
    """Asserts that deceptive persona prompts trigger a BLOCKING violation."""
    # Find matching filename in case the name is truncated
    fixture = next(EXAMPLES_DIR.glob("pr_violation_deceptive_pr*.py"))
    report = audit_file(fixture)

    assert report.status == "FAILED"
    assert report.blocking_violations >= 1
    
    flagged_rules = [v.rule_id for v in report.violations]
    assert any("art50" in r or "transparency" in r or "deceptive" in r for r in flagged_rules)


def test_duaa_adm_violation_fails():
    """Asserts that solely automated decisions lacking escalation trigger a BLOCKING violation."""
    fixture = EXAMPLES_DIR / "pr_violation_duaa_adm.py"
    report = audit_file(fixture)

    assert report.status == "FAILED"
    assert report.blocking_violations >= 1

    flagged_rules = [v.rule_id for v in report.violations]
    assert any("duaa" in r or "adm" in r or "art22c" in r for r in flagged_rules)