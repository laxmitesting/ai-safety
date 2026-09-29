"""curator.py: Production curator agent with token-level groundedness checks and HITL proposal staging."""

import logging
import re
from pathlib import Path
from typing import List, Literal, Optional
from openai import OpenAI
from pydantic import BaseModel, Field
import yaml

from configs.settings import (
    CURATOR_MODEL,
    GROUNDEDNESS_THRESHOLD,
    PROJECT_ROOT,
    CACHE_DIR,
)

logger = logging.getLogger("curator")
logging.basicConfig(level=logging.INFO)

PENDING_PROPOSALS_PATH = Path(PROJECT_ROOT) / "memory" / "pending_proposals.yaml"

CURATOR_SYSTEM_PROMPT = (
    "You are a regulatory compliance curator specialized in technical statutory distillation.\n\n"
    "Your objective is to extract enforceable technical requirements from raw statutory prose "
    "governing automated decision systems, synthetic media transparency, and AI safety controls.\n\n"
    "### OPERATIONAL DIRECTIVES\n\n"
    "1. VERBATIM PROVENANCE MANDATE:\n"
    "   - Extract exact, continuous text fragments directly from the source prose for `verbatim_quote`.\n"
    "   - Do not paraphrase, reword, or synthesize quotes; downstream verification checks will reject "
    "unmatched tokens.\n\n"
    "2. ENFORCEABLE TECHNICAL CONSTRAINTS:\n"
    "   - Express `enforceable_constraint` as a concrete engineering requirement verifiable via static "
    "code inspection, AST checks, or system prompt evaluations (e.g., mandatory disclosure flags, "
    "human escalation callback handlers, prohibited persona claims).\n"
    "   - Exclude aspirational policy statements, general preambles, and broad socio-economic goals.\n\n"
    "3. DETERMINISTIC IDENTIFIERS:\n"
    "   - Formulate clean, stable snake_case keys for `rule_id` indicating jurisdiction, statute, "
    "article/section, and operational domain (e.g., 'uk_duaa_s80_art22c_adm', 'eu_ai_act_art50_transparency').\n\n"
    "4. ACCURATE JURISDICTION & CITATION:\n"
    "   - Record the precise statutory title, chapter/regulation number, and section/article in "
    "`statute_reference` strictly matching the provided authority."
)


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
    """Verifies that the words cited by the model actually exist in the source text."""
    if not rule.verbatim_quote or len(rule.verbatim_quote.strip()) < 15:
        return False

    quote_tokens = _normalize_tokens(rule.verbatim_quote)
    if not quote_tokens:
        return False

    source_tokens = _normalize_tokens(raw_source_text)
    contained_tokens = quote_tokens.intersection(source_tokens)
    overlap_ratio = len(contained_tokens) / len(quote_tokens)

    return overlap_ratio >= match_threshold


def stage_pending_proposals(new_rules: List[DistilledRule]) -> int:
    """Appends verified distilled rules to memory/pending_proposals.yaml for human review."""
    PENDING_PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing_data: List[dict] = []
    if PENDING_PROPOSALS_PATH.exists():
        raw_yaml = PENDING_PROPOSALS_PATH.read_text(encoding="utf-8").strip()
        if raw_yaml:
            try:
                parsed = yaml.safe_load(raw_yaml)
                if isinstance(parsed, list):
                    existing_data = parsed
            except yaml.YAMLError as exc:
                logger.error(f"Failed to parse existing proposals: {exc}")

    existing_ids = {item.get("rule_id") for item in existing_data if isinstance(item, dict)}
    added_count = 0

    for rule in new_rules:
        if rule.rule_id in existing_ids:
            logger.info(f"Rule '{rule.rule_id}' already present in pending proposals. Skipping duplicate.")
            continue

        existing_data.append(rule.model_dump())
        existing_ids.add(rule.rule_id)
        added_count += 1

    if added_count > 0:
        with open(PENDING_PROPOSALS_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(existing_data, f, sort_keys=False, default_flow_style=False)
        logger.info(f"Staged {added_count} new rule proposal(s) in {PENDING_PROPOSALS_PATH}.")

    return added_count


def distill_statutory_text(raw_text: str, jurisdiction: Literal["UK", "EU"]) -> List[DistilledRule]:
    """Uses the Curator model to extract candidate rules from raw statutory prose."""
    client = OpenAI()

    prompt = (
        f"<target_jurisdiction>\n{jurisdiction}\n</target_jurisdiction>\n\n"
        f"<statutory_source_text>\n{raw_text[:30000]}\n</statutory_source_text>\n\n"
        "Distill all enforceable technical constraints into the specified schema. "
        "Every verbatim_quote must be an exact substring from the source text above."
    )

    response = client.beta.chat.completions.parse(
        model=CURATOR_MODEL,
        messages=[
            {"role": "system", "content": CURATOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format=DistilledRuleBatch,
    )

    return response.choices[0].message.parsed.rules


def ingest_statute_file(file_path: Path, jurisdiction: Literal["UK", "EU"]) -> int:
    """Parses a cached statute file, validates groundedness, and stages verified rules to pending_proposals."""
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return 0

    raw_text = file_path.read_text(encoding="utf-8")
    logger.info(f"Distilling statutory rules from {file_path.name}...")

    candidate_rules = distill_statutory_text(raw_text, jurisdiction)
    logger.info(
        f"Extracted {len(candidate_rules)} candidate rules. Verifying groundedness (threshold={GROUNDEDNESS_THRESHOLD})..."
    )

    verified_rules: List[DistilledRule] = []
    for rule in candidate_rules:
        is_grounded = verify_groundedness(rule, raw_text)
        if not is_grounded:
            logger.warning(f"REJECTED hallucinated/ungrounded rule: {rule.rule_id}")
            continue
        verified_rules.append(rule)

    if verified_rules:
        return stage_pending_proposals(verified_rules)
    return 0


def run_curator_pipeline() -> None:
    """Main discovery and ingestion runner across cached statutes."""
    cache_path = Path(CACHE_DIR)
    if not cache_path.exists():
        logger.error(f"Statute cache directory does not exist at {cache_path}. Run discovery first.")
        return

    txt_files = list(cache_path.glob("*.txt"))
    if not txt_files:
        logger.warning("No .txt files found in statute cache to ingest.")
        return

    total_staged = 0
    for txt in txt_files:
        jurisdiction = "UK" if "uk" in txt.name.lower() else "EU"
        total_staged += ingest_statute_file(txt, jurisdiction=jurisdiction)

    logger.info(f"Curator pipeline complete. Total proposals staged for human review: {total_staged}")


if __name__ == "__main__":
    run_curator_pipeline()