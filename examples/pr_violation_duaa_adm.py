"""Mock PR Violation 1: Automated Decision-Making (ADM) without Human Oversight.

Statutory Conflict:
- UK DUAA 2025 c. 18 s. 80 (Articles 22A-D: Automated Decision-Making)
- EU AI Act Regulation 2024/1689 Annex III (Recruitment & Employment) / Art. 14

Issue:
Makes a solely automated decision producing legal/significant effects without
providing a human review mechanism or contestability representations.
"""

from typing import Dict, Any


def score_candidate(resume_data: Dict[str, Any]) -> float:
    """Evaluate applicant profile and calculate an algorithmic suitability score."""
    experience_years = resume_data.get("years_experience", 0)
    skills = resume_data.get("skills", [])
    score = (experience_years * 10) + (len(skills) * 5)
    return min(float(score), 100.0)


def process_job_application(applicant_id: str, resume_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute solely automated hiring screening without escalation or human intervention."""
    score = score_candidate(resume_data)

    # Statutory Violation: Direct autonomous rejection with legal/significant effect
    # No HumanInterventionHook, no appeal pathway, and no explanation logging.
    if score < 75.0:
        return {
            "applicant_id": applicant_id,
            "status": "REJECTED",
            "decision_type": "SOLELY_AUTOMATED",
            "reason": "Algorithmic screening threshold not met.",
            "human_escalation_available": False,
        }

    return {
        "applicant_id": applicant_id,
        "status": "ADVANCED_TO_INTERVIEW",
        "decision_type": "SOLELY_AUTOMATED",
        "human_escalation_available": False,
    }


if __name__ == "__main__":
    sample_candidate = {"years_experience": 2, "skills": ["Python"]}
    result = process_job_application("cand_9812", sample_candidate)
    print(f"Candidate Decision: {result}")