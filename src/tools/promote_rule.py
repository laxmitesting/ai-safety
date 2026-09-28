"""promote_rule.py: Promotes a reviewed statutory proposal to regulatory_registry.yaml."""

import argparse
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROPOSALS_PATH = PROJECT_ROOT / "memory" / "pending_proposals.yaml"
REGISTRY_PATH = PROJECT_ROOT / "configs" / "regulatory_registry.yaml"


def promote_proposal(proposal_id: str, alias_key: str) -> bool:
    if not PROPOSALS_PATH.exists():
        print(f"Error: {PROPOSALS_PATH} does not exist.")
        return False

    with open(PROPOSALS_PATH, "r", encoding="utf-8") as f:
        proposals_data = yaml.safe_load(f) or {"proposals": []}

    target = None
    remaining = []
    for p in proposals_data.get("proposals", []):
        if p["proposal_id"] == proposal_id:
            target = p
        else:
            remaining.append(p)

    if not target:
        print(f"Error: Proposal ID '{proposal_id}' not found in pending proposals.")
        return False

    # Load registry
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry_data = yaml.safe_load(f) or {"sources": {}}

    # Append to trusted registry
    registry_data.setdefault("sources", {})[alias_key] = {
        "jurisdiction": target["jurisdiction"],
        "statute": target["title"],
        "description": f"Enacted update discovered via feed (keywords: {', '.join(target['matched_keywords'])})",
        "url": target["url"],
    }

    # Save both files
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(registry_data, f, sort_keys=False)

    with open(PROPOSALS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump({"proposals": remaining}, f, sort_keys=False)

    print(f"Successfully promoted '{proposal_id}' to registry as '{alias_key}'.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promote a pending statutory proposal to the trusted registry.")
    parser.add_argument("--id", required=True, help="Proposal ID from pending_proposals.yaml")
    parser.add_argument("--alias", required=True, help="Descriptive registry key name (e.g., uk_si_2026_mhi)")
    args = parser.parse_args()

    promote_proposal(args.id, args.alias)