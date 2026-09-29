"""promote_rule.py: Promotes a reviewed statutory proposal to regulatory_registry.yaml and Qdrant."""

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from qdrant_client import models

from configs.settings import (
    EMBEDDING_DIM,
    PROJECT_ROOT,
)
from src.tools.qdrant_client import get_embedding, get_qdrant_client

logger = logging.getLogger("promote_rule")
logging.basicConfig(level=logging.INFO)

COLLECTION_NAME = "statutory_rules"
PROPOSALS_PATH = Path(PROJECT_ROOT) / "memory" / "pending_proposals.yaml"
REGISTRY_PATH = Path(PROJECT_ROOT) / "configs" / "regulatory_registry.yaml"


def _load_proposals() -> List[Dict[str, Any]]:
    """Loads proposals supporting both flat list and nested {'proposals': [...]} formats."""
    if not PROPOSALS_PATH.exists():
        logger.error(f"{PROPOSALS_PATH} does not exist.")
        return []

    raw = PROPOSALS_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    data = yaml.safe_load(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("proposals", [])
    return []


def _save_proposals(remaining: List[Dict[str, Any]]) -> None:
    """Saves remaining pending proposals back to disk as a clean list."""
    with open(PROPOSALS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(remaining, f, sort_keys=False, default_flow_style=False)


def _index_in_qdrant(rule_data: Dict[str, Any]) -> None:
    """Upserts the approved statutory rule into the Qdrant vector collection."""
    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME not in collections:
        logger.info(f"Creating Qdrant collection '{COLLECTION_NAME}' (dim={EMBEDDING_DIM})...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        )

    # Build semantic anchor payload
    statute_ref = rule_data.get("statute_reference") or rule_data.get("statute") or "N/A"
    constraint = rule_data.get("enforceable_constraint") or rule_data.get("description") or ""
    verbatim = rule_data.get("verbatim_quote") or ""
    rule_id = rule_data.get("rule_id") or rule_data.get("proposal_id") or "unnamed_rule"

    embedding_payload = f"{statute_ref} | {constraint} | {verbatim}"
    vector = get_embedding(embedding_payload)
    point_id = abs(hash(rule_id)) % (10 ** 12)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload=rule_data,
            )
        ],
    )
    logger.info(f"Indexed rule '{rule_id}' into Qdrant collection '{COLLECTION_NAME}'.")


def promote_proposal(proposal_id: str, alias_key: Optional[str] = None) -> bool:
    """Promotes a proposal by ID, updates registry, and indexes vectors."""
    all_proposals = _load_proposals()
    if not all_proposals:
        print(f"Error: No proposals found in {PROPOSALS_PATH}.")
        return False

    target: Optional[Dict[str, Any]] = None
    remaining: List[Dict[str, Any]] = []

    for p in all_proposals:
        # Check against rule_id or proposal_id
        pid = p.get("rule_id") or p.get("proposal_id")
        if pid == proposal_id:
            target = p
        else:
            remaining.append(p)

    if not target:
        print(f"Error: Proposal ID '{proposal_id}' not found in pending proposals.")
        return False

    effective_alias = alias_key or proposal_id

    # 1. Update configs/regulatory_registry.yaml
    registry_data: Dict[str, Any] = {"sources": {}}
    if REGISTRY_PATH.exists():
        raw_reg = REGISTRY_PATH.read_text(encoding="utf-8").strip()
        if raw_reg:
            registry_data = yaml.safe_load(raw_reg) or {"sources": {}}

    registry_data.setdefault("sources", {})[effective_alias] = {
        "jurisdiction": target.get("jurisdiction", "UNKNOWN"),
        "statute": target.get("statute_reference") or target.get("title") or effective_alias,
        "constraint": target.get("enforceable_constraint", ""),
        "verbatim_quote": target.get("verbatim_quote", ""),
        "url": target.get("url", ""),
    }

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(registry_data, f, sort_keys=False, default_flow_style=False)

    # 2. Index into Qdrant vector store
    try:
        _index_in_qdrant(target)
    except Exception as exc:
        logger.warning(f"Could not index to Qdrant (continuing registry update): {exc}")

    # 3. Update pending_proposals.yaml
    _save_proposals(remaining)

    print(f"✅ Successfully promoted '{proposal_id}' to registry as '{effective_alias}'.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promote a pending statutory proposal to registry and vector store.")
    parser.add_argument("--id", "--rule-id", dest="proposal_id", required=True, help="Rule/Proposal ID from pending_proposals.yaml")
    parser.add_argument("--alias", default=None, help="Optional descriptive registry key name (defaults to ID)")
    args = parser.parse_args()

    promote_proposal(args.proposal_id, args.alias)