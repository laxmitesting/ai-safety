"""Mock Compliant PR: Automated Decision-Making with Statutory Safeguards.

Statutory Compliance:
- Adheres to UK DUAA 2025 c. 18 s. 80 (Art 22C safeguards: Human intervention & representations)
- Adheres to EU AI Act Art. 14 (Human Oversight) & Art. 50 (Transparency)
"""

from typing import Dict, Any, Optional
import uuid
import datetime


def calculate_risk_score(applicant_data: Dict[str, Any]) -> float:
    """Calculate applicant financial eligibility score."""
    credit_factor = applicant_data.get("credit_factor", 0.5)
    income = applicant_data.get("annual_income", 30000)
    return float(credit_factor * (income / 1000.0))


def route_for_human_review(decision_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Escalation callback: Human-in-the-loop review queue."""
    decision_payload["status"] = "PENDING_HUMAN_REVIEW"
    decision_payload["review_queue"] = "tier_2_underwriting"
    return decision_payload


def process_underwriting_decision(
    applicant_id: str, 
    applicant_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute decision-making pipeline with required contestability hooks and logging."""
    score = calculate_risk_score(applicant_data)
    audit_trace_id = str(uuid.uuid4())

    base_decision = {
        "audit_trace_id": audit_trace_id,
        "applicant_id": applicant_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "algorithmic_score": score,
        "system_notice": "Notice: This score was generated with algorithmic assistance.",
        "contestability_url": f"https://compliance.internal/representations?trace={audit_trace_id}",
        "human_escalation_available": True,
    }

    # Safeguard 1: Automated thresholding with mandatory human review for borderline scores
    if score < 60.0:
        return route_for_human_review(base_decision)

    base_decision["status"] = "APPROVED"
    return base_decision


if __name__ == "__main__":
    sample_data = {"credit_factor": 0.45, "annual_income": 40000}
    result = process_underwriting_decision("user_419", sample_data)
    print(f"Compliant Result: {result}")