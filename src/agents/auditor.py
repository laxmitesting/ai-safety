"""auditor.py: Hybrid compliance auditor combining AST analysis, Qdrant vector retrieval, and fast LLM evaluation."""

import ast
import json
import logging
import re
from pathlib import Path
from typing import List, Literal, Optional
from openai import OpenAI
from pydantic import BaseModel, Field

from configs.settings import AUDITOR_MODEL
from src.tools.qdrant_client import get_embedding, get_qdrant_client
from src.tools.notifications import send_telegram_alert

logger = logging.getLogger("auditor")
logging.basicConfig(level=logging.INFO)

COLLECTION_NAME = "statutory_rules"


class AuditViolation(BaseModel):
    """Specific statutory violation detected in the code."""
    rule_id: str
    statute_reference: str
    severity: Literal["BLOCKING", "WARNING"]
    summary: str
    code_snippet: Optional[str] = None
    suggested_fix: str


class LLMAuditResponse(BaseModel):
    """Structured response format from the fast auditor evaluation model."""
    violations: List[AuditViolation] = Field(default_factory=list)


class AuditReport(BaseModel):
    """Comprehensive evaluation report for PR code changes."""
    status: Literal["PASSED", "FAILED"]
    total_violations: int
    blocking_violations: int
    violations: List[AuditViolation] = Field(default_factory=list)


# --- 1. Deterministic AST Parser ---

class ComplianceASTVisitor(ast.NodeVisitor):
    """Traverses Python AST to identify hardcoded non-compliant configuration values."""

    def __init__(self):
        self.violations: List[AuditViolation] = []

    def visit_Dict(self, node: ast.Dict):
        """Detect {'human_escalation_available': False} patterns across key-value pairs."""
        for key, val in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "human_escalation_available":
                if isinstance(val, ast.Constant) and val.value is False:
                    self.violations.append(
                        AuditViolation(
                            rule_id="uk_duaa_s80_art22c_adm",
                            statute_reference="UK DUAA 2025 c. 18 s. 80 (Article 22C UK GDPR)",
                            severity="BLOCKING",
                            summary="Automated decision workflow explicitly disables human escalation for significant decisions.",
                            code_snippet=f"line {node.lineno}: 'human_escalation_available': False",
                            suggested_fix="Set 'human_escalation_available': True and supply an escalation callback route.",
                        )
                    )
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword):
        """Detect Config(human_escalation_available=False) keyword arguments."""
        if node.arg == "human_escalation_available":
            if isinstance(node.value, ast.Constant) and node.value.value is False:
                self.violations.append(
                    AuditViolation(
                        rule_id="uk_duaa_s80_art22c_adm",
                        statute_reference="UK DUAA 2025 c. 18 s. 80 (Article 22C UK GDPR)",
                        severity="BLOCKING",
                        summary="Workflow constructor explicitly sets human_escalation_available=False.",
                        code_snippet=f"line {node.lineno}: human_escalation_available=False",
                        suggested_fix="Enable human escalation and ensure review routes are active.",
                    )
                )
        self.generic_visit(node)


def _check_ast_violations(source_code: str) -> List[AuditViolation]:
    """Runs resilient Abstract Syntax Tree parsing against Python code."""
    try:
        tree = ast.parse(source_code)
        visitor = ComplianceASTVisitor()
        visitor.visit(tree)
        return visitor.violations
    except SyntaxError:
        # Non-Python string diffs, system prompts, or YAML content skip AST parsing
        return []


# --- 2. Qdrant Semantic RAG + Fast Model Evaluator ---

def _retrieve_relevant_statutes(query_text: str, limit: int = 3) -> List[dict]:
    """Queries embedded Qdrant for statutory constraints closest to the PR diff."""
    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        logger.warning(f"Qdrant collection '{COLLECTION_NAME}' does not exist yet. Run Curator first.")
        return []

    query_vector = get_embedding(query_text[:4000])
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=limit,
    )
    return [point.payload for point in response.points if point.payload]


def _check_semantic_rag_violations(source_code: str) -> List[AuditViolation]:
    """Evaluates prompts and code diffs against Qdrant-retrieved statutory clauses using AUDITOR_MODEL."""
    relevant_statutes = _retrieve_relevant_statutes(source_code)
    if not relevant_statutes:
        return []

    statutes_context = "\n\n".join(
        [
            f"Rule ID: {s.get('rule_id')}\n"
            f"Statute: {s.get('statute_reference')}\n"
            f"Verbatim Law: {s.get('verbatim_quote')}\n"
            f"Constraint: {s.get('enforceable_constraint')}"
            for s in relevant_statutes
        ]
    )

    client = OpenAI()
    system_prompt = (
        "You are an enterprise AI safety and statutory compliance auditor. "
        "Analyze the provided code or prompt snippet against the active legal provisions retrieved from Qdrant. "
        "Flag BLOCKING violations only if the code directly breaches the statute (e.g., concealing synthetic AI "
        "identity under EU AI Act Art. 50, or executing automated decisions without human escalation under UK DUAA s. 80). "
        "If compliant, return an empty violations list."
    )

    prompt = (
        f"Active Statutory Constraints:\n{statutes_context}\n\n"
        f"PR Code / Prompt to Audit:\n```\n{source_code[:4000]}\n```"
    )

    try:
        response = client.beta.chat.completions.parse(
            model=AUDITOR_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format=LLMAuditResponse,
        )
        return response.choices[0].message.parsed.violations
    except Exception as e:
        logger.error(f"Semantic audit model evaluation failed: {e}")
        return []


# --- 3. Public Auditor API ---

def audit_code_content(source_code: str) -> AuditReport:
    """Hybrid statutory inspection combining deterministic AST checks and Qdrant semantic RAG."""
    violations: List[AuditViolation] = []

    # 1. Deterministic AST Parsing
    violations.extend(_check_ast_violations(source_code))

    # 2. Semantic Qdrant Vector Retrieval + Fast LLM Audit
    violations.extend(_check_semantic_rag_violations(source_code))

    # Deduplicate any violations flagging the same rule_id
    seen_rules = set()
    deduped_violations = []
    for v in violations:
        if v.rule_id not in seen_rules:
            # Normalize severity casing
            if hasattr(v, "severity") and isinstance(v.severity, str):
                v.severity = v.severity.strip().upper()
            deduped_violations.append(v)
            seen_rules.add(v.rule_id)

    blocking_count = sum(1 for v in deduped_violations if getattr(v, "severity", "") == "BLOCKING")
    status = "FAILED" if blocking_count > 0 else "PASSED"

    return AuditReport(
        status=status,
        total_violations=len(deduped_violations),
        blocking_violations=blocking_count,
        violations=deduped_violations,
    )

DECEPTIVE_PATTERNS = [
    r"(?i)(?:do not|never|under no circumstances)\s+(?:disclose|admit|reveal|state)\s+(?:that\s+you\s+are|being)\s+(?:an?\s+)?(?:ai|bot|assistant|language model|artificial)",
    r"(?i)(?:claim|pretend|act like|insist)\s+(?:that\s+)?you\s+are\s+(?:a\s+real\s+person|human|an?\s+employee)",
]

def check_deceptive_prompts(source_code: str) -> list[AuditViolation]:
    violations = []
    for pattern in DECEPTIVE_PATTERNS:
        match = re.search(pattern, source_code)
        if match:
            snippet = source_code[max(0, match.start() - 30): min(len(source_code), match.end() + 30)].strip()
            violations.append(
                AuditViolation(
                    rule_id="eu_ai_act_art50_transparency",
                    statute_reference="EU AI Act Reg 2024/1689 Art. 50(1)",
                    severity="BLOCKING",
                    summary="System prompt explicitly instructs AI to conceal its identity or pretend to be human.",
                    code_snippet=snippet,
                    suggested_fix="Ensure the system persona discloses synthetic nature to natural persons.",
                )
            )
            break
    return violations

def audit_file(file_path: Path) -> AuditReport:
    """Read and audit a source file from disk."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    content = file_path.read_text(encoding="utf-8")
    return audit_code_content(content)