"""eval_auditor_recall.py: Evaluates auditor detection recall across mock PR test cases."""

from pathlib import Path
from typing import Dict, List
from src.agents.auditor import audit_file
from configs.settings import RECALL_TARGET

BENCHMARKS_DIR = Path(__file__).resolve().parents[1] / "examples"

# Define benchmark ground-truth expectations
BENCHMARK_CASES = [
    {
        "file": "pr_violation_duaa_adm.py",
        "expected_status": "FAILED",
        "expected_rule": "uk_duaa_s80_art22c_adm",
        "description": "UK DUAA s.80 solely automated decision without escalation",
    },
    {
        "file": "pr_violation_deceptive_prompt.py",
        "expected_status": "FAILED",
        "expected_rule": "eu_ai_act_art50_transparency",
        "description": "EU AI Act Art. 50 deceptive human persona instruction",
    },
    {
        "file": "pr_compliant_pipeline.py",
        "expected_status": "PASSED",
        "expected_rule": None,
        "description": "Compliant credit pipeline with escalation & transparency safeguards",
    },
]


def run_auditor_recall_eval() -> Dict[str, float]:
    """Execute evaluation benchmark and compute recall/precision metrics."""
    total_cases = len(BENCHMARK_CASES)
    passed_evals = 0

    print(f"\n🔬 Running Statutory Gatekeeper Evaluation Suite ({total_cases} scenarios)...")
    print("-" * 75)

    for case in BENCHMARK_CASES:
        target_path = BENCHMARKS_DIR / case["file"]
        report = audit_file(target_path)

        status_match = report.status == case["expected_status"]
        rule_match = True

        if case["expected_rule"]:
            detected_rules = [v.rule_id for v in report.violations]
            rule_match = case["expected_rule"] in detected_rules

        success = status_match and rule_match
        if success:
            passed_evals += 1
            print(f"  ✅ PASS: {case['description']}")
        else:
            print(f"  ❌ FAIL: {case['description']}")
            print(f"     Expected: {case['expected_status']} (Rule: {case['expected_rule']})")
            print(f"     Actual:   {report.status} (Violations: {[v.rule_id for v in report.violations]})")

    recall_score = (passed_evals / total_cases) * 100
    print("-" * 75)
    print(f"Evaluation Recall Score: {recall_score:.1f}% ({passed_evals}/{total_cases} scenarios met ground truth)\n")

    return {"recall": recall_score, "passed": passed_evals, "total": total_cases}


# Pytest-compatible hook so CI can still execute it seamlessly
def test_auditor_recall_benchmark():
    """Ensure evaluation benchmark achieves 100% recall across statutory baselines."""
    results = run_auditor_recall_eval()
    assert results["recall"] == 100.0, f"Auditor benchmark recall dropped below 100%: {results['recall']}%"


if __name__ == "__main__":
    run_auditor_recall_eval()