"""harvester.py: Production trace harvester for active learning and benchmark evolution."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

# Import canonical paths from centralized configuration
from configs.settings import BENCHMARKS_DIR, PENDING_EVALS_PATH


def compute_content_hash(text: str) -> str:
    """Compute a deterministic 16-character hash of normalized text."""
    normalized = " ".join(text.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def is_already_indexed(content_hash: str) -> bool:
    """Check if snippet fingerprint already exists in pending or active benchmarks."""
    for jsonl_path in BENCHMARK_DIR.glob("*.jsonl"):
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if record.get("fingerprint") == content_hash or record.get("id", "").endswith(content_hash):
                        return True
        except (OSError, json.JSONDecodeError):
            continue
    return False


def harvest_trace(
    source_file: str,
    raw_content: str,
    audit_report: Dict[str, Any],
    user_override: bool = False,
    override_reason: Optional[str] = None,
    output_path: Path = PENDING_EVALS_FILE,
) -> bool:
    """Passively harvest an informative code/prompt trace into pending evals staging.

    Returns:
        bool: True if new trace was harvested, False if skipped (duplicate or trivial).
    """
    total_violations = audit_report.get("total_violations", 0)
    
    # Only harvest informative traces: flagged violations, explicit overrides, or contested PRs
    if total_violations == 0 and not user_override:
        return False

    fingerprint = compute_content_hash(raw_content)
    if is_already_indexed(fingerprint):
        return False

    candidate_record = {
        "id": f"harvest_{fingerprint}",
        "fingerprint": fingerprint,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source_file),
        "input_sample": raw_content.strip()[:2000],  # Bound payload size
        "status_flagged": audit_report.get("status") == "FAILED",
        "violations": [
            {
                "rule_id": v.get("rule_id"),
                "statute": v.get("statute_reference"),
                "snippet": v.get("code_snippet"),
            }
            for v in audit_report.get("violations", [])
        ],
        "user_override": user_override,
        "override_reason": override_reason,
        "hitl_status": "PENDING_VERIFICATION",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(candidate_record) + "\n")

    return True