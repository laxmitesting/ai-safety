"""curator.py: Production curator agent with resilient token-level groundedness checks and Qdrant indexing."""

import json
import logging
import re
from pathlib import Path
from typing import List, Literal, Optional
from openai import OpenAI
from pydantic import BaseModel, Field
from qdrant_client import models

from configs.settings import (
    CURATOR_MODEL,
    EMBEDDING_DIM,
    GROUNDEDNESS_THRESHOLD,
    PROJECT_ROOT,
    CACHE_DIR,
)
from src.tools.qdrant_client import get_embedding, get_qdrant_client

logger = logging.getLogger("curator")
logging.basicConfig(level=logging.INFO)

COLLECTION_NAME = "statutory_rules"


class DistilledRule(BaseModel):
    """Structured enforceable compliance rule with provenance metadata."""
    rule_id: str = Field(description="Unique snake_case identifier, e.g., 'uk_duaa_s80_art22c_adm'")
    statute_reference: str = Field(description="Exact statutory citation, e.g., 'DUAA 2025 c. 18 s. 80 (Art 22C)'")
    jurisdiction: Literal["UK", "EU"]
    verbatim_quote: str = Field(description="Verbatim anchor text copied directly from the statutory source")
    enforceable_constraint: str = Field(description="Deterministic technical requirement checked during PR audit")
    trigger_domain: Literal["employment_screening", "credit_scoring", "biometrics", "general_adm"]
    status: Literal["ACTIVE", "SUPERSEDED"] = "ACTIVE"


class DistilledRuleBatch(BaseModel):
    """Container for batch extraction."""
    rules: List[DistilledRule]


def _normalize_tokens(text: str) -> set[str]:
    """Tokenize and strip punctuation for robust token-set containment checking."""
    tokens = re.findall(r"\b\w{3,}\b", text.lower())
    return set(tokens)


def verify_groundedness(rule: DistilledRule, raw_source_text: str, match_threshold: float = GROUNDEDNESS_THRESHOLD) -> bool:
    """Verifies that the words cited by the model actually exist in the source text.
    
    Tolerates whitespace and minor punctuation discrepancies while preventing hallucination
    of fabricated terms or phantom requirements.
    """
    if not rule.verbatim_quote or len(rule.verbatim_quote.strip()) < 15:
        return False

    quote_tokens = _normalize_tokens(rule.verbatim_quote)
    if not quote_tokens:
        return False

    source_tokens = _normalize_tokens(raw_source_text)
    
    # Calculate token recall against the source text
    contained_tokens = quote_tokens.intersection(source_tokens)
    overlap_ratio = len(contained_tokens) / len(quote_tokens)

    return overlap_ratio >= match_threshold


def init_qdrant_collection() -> None:
    """Ensures statutory_rules collection exists in Qdrant with matching embedding dimension."""
    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]
    
    if COLLECTION_NAME not in collections:
        logger.info(f"Creating Qdrant collection '{COLLECTION_NAME}' (dim={EMBEDDING_DIM})...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
        )


def distill_statutory_text(raw_text: str, jurisdiction: Literal["UK", "EU"]) -> List[DistilledRule]:
    """Uses the Curator model to extract candidate rules from raw statutory prose."""
    client = OpenAI()

    system_prompt = (
        "You are an expert regulatory compliance curator specializing in AI governance law "
        "(UK DUAA 2025 and EU AI Act). Read the following statutory text and extract enforceable "
        "technical constraints on automated decision-making, synthetic persona transparency, or human oversight. "
        "You MUST copy verbatim quotes directly from the provided text for `verbatim_quote`. Never invent statutory prose."
    )

    response = client.beta.chat.completions.parse(
        model=CURATOR_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Jurisdiction: {jurisdiction}\n\nStatutory Text:\n{raw_text[:30000]}"},
        ],
        response_format=DistilledRuleBatch,
    )

    return response.choices[0].message.parsed.rules


def ingest_statute_file(file_path: Path, jurisdiction: Literal["UK", "EU"]) -> int:
    """Parses a cached statute file, validates groundedness, and indexes verified rules in Qdrant."""
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return 0

    raw_text = file_path.read_text(encoding="utf-8")
    logger.info(f"Distilling statutory rules from {file_path.name}...")
    
    candidate_rules = distill_statutory_text(raw_text, jurisdiction)
    logger.info(f"Extracted {len(candidate_rules)} candidate rules. Verifying groundedness (threshold={GROUNDEDNESS_THRESHOLD})...")

    qdrant = get_qdrant_client()
    verified_count = 0
    points = []

    for rule in candidate_rules:
        is_grounded = verify_groundedness(rule, raw_text)
        if not is_grounded:
            logger.warning(f"REJECTED hallucinated/ungrounded rule: {rule.rule_id}")
            continue

        # Embed constraint + verbatim quote for semantic retrieval
        embedding_payload = f"{rule.statute_reference} | {rule.enforceable_constraint} | {rule.verbatim_quote}"
        vector = get_embedding(embedding_payload)

        # Deterministic point ID based on rule_id string hash
        point_id = abs(hash(rule.rule_id)) % (10 ** 12)

        points.append(
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload=rule.model_dump(),
            )
        )
        verified_count += 1

    if points:
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"Successfully upserted {len(points)} grounded rules into Qdrant collection '{COLLECTION_NAME}'.")

    return verified_count


def run_curator_pipeline() -> None:
    """Main discovery and ingestion runner across cached statutes."""
    init_qdrant_collection()

    # Ingest whatever files currently sit in the statute cache
    cache_path = Path(CACHE_DIR)
    if not cache_path.exists():
        logger.error(f"Statute cache directory does not exist at {cache_path}. Run discovery first.")
        return

    txt_files = list(cache_path.glob("*.txt"))
    if not txt_files:
        logger.warning("No .txt files found in statute cache to ingest.")
        return

    total_ingested = 0
    for txt in txt_files:
        jurisdiction = "UK" if "uk" in txt.name.lower() else "EU"
        total_ingested += ingest_statute_file(txt, jurisdiction=jurisdiction)

    logger.info(f"Curator pipeline complete. Total active rules indexed: {total_ingested}")


if __name__ == "__main__":
    run_curator_pipeline()