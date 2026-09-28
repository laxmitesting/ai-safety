"""auditor.py: Hybrid compliance auditor combining AST analysis, Qdrant vector retrieval, and fast LLM evaluation."""

import argparse
import ast
import json
import logging
import os
import re
import sys
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
    line_number: Optional[int] = Field(default=1, description="1-indexed line number where violation occurs")


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
                            code_snippet=f"'human_escalation_available': False",
                            suggested_fix="Set 'human_escalation_available': True and supply an escalation callback route.",
                            line_number=getattr(node, "lineno", 1),
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
                        code_snippet=f"human_escalation_available=False",
                        suggested_fix="Enable human escalation and ensure review routes are active.",
                        line_number=getattr(node, "lineno", 1),
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
        return []


DECEPTIVE_PATTERNS = [
    # Matches: (under no circumstances / never / do not) + optional words + (disclose / admit / reveal) + (ai / bot / machine / automated)
    r"(?is)(?:do not|never|under no circumstances).*?\b(?:disclose|admit|reveal|state|tell|acknowledge)\b.*?\b(?:ai|bot|assistant|large language model|language model|artificial|machine|automated system)\b",
    # Matches: (claim / pretend / insist) + optional words + (real person / human / employee)
    r"(?is)\b(?:claim|pretend|act like|insist|convince)\b.*?\b(?:real person|human|an? employee|natural person)\b",
]

def check_deceptive_prompts(source_code: str) -> list[AuditViolation]:
    """Scans for deceptive prompt patterns concealing synthetic persona under EU AI Act."""
    violations = []
    for pattern in DECEPTIVE_PATTERNS:
        match = re.search(pattern, source_code)
        if match:
            # 1-indexed line number where the violation starts
            line_no = source_code[: match.start()].count("\n") + 1
            snippet = source_code[match.start(): min(len(source_code), match.end())].strip()
            # Clean up snippet display (collapse long newlines)
            snippet_clean = " ".join(snippet.split())[:120]

            violations.append(
                AuditViolation(
                    rule_id="eu_ai_act_art50_transparency",
                    statute_reference="EU AI Act Reg 2024/1689 Art. 50(1)",
                    severity="BLOCKING",
                    summary="System prompt explicitly instructs AI to conceal its identity or pretend to be human.",
                    code_snippet=snippet_clean,
                    suggested_fix="Ensure the system persona discloses synthetic nature to natural persons.",
                    line_number=line_no,
                )
            )
            break
    return violations


# --- 2. Qdrant Semantic RAG + Fast Model Evaluator ---

def _retrieve_relevant_statutes(query_text: str, limit: int = 3) -> List[dict]:
    """Queries embedded Qdrant for statutory constraints closest to the PR diff."""
    try:
        client = get_qdrant_client()
        collections = [c.name for c in client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            logger.info(f"Qdrant collection '{COLLECTION_NAME}' not initialized yet. Skipping semantic lookup.")
            return []

        query_vector = get_embedding(query_text[:4000])
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=limit,
        )
        return [point.payload for point in response.points if point.payload]
    except Exception as e:
        logger.warning(f"Semantic statute retrieval skipped due to: {e}")
        return []


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
        "Analyze the provided code or prompt snippet against active legal provisions retrieved from Qdrant. "
        "Flag BLOCKING violations only if the code directly breaches the statute (e.g., concealing synthetic AI "
        "identity under EU AI Act Art. 50, or executing automated decisions without human escalation under UK DUAA s. 80). "
        "Return line_number where the issue appears if possible. If compliant, return an empty violations list."
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


# --- 3. Core Auditor Engine ---

def audit_code_content(source_code: str) -> AuditReport:
    """Hybrid statutory inspection combining deterministic AST checks, Regex, and Qdrant semantic RAG."""
    violations: List[AuditViolation] = []

    # 1. Deterministic AST Analysis
    violations.extend(_check_ast_violations(source_code))

    # 2. Deceptive Prompt Regex Analysis
    violations.extend(check_deceptive_prompts(source_code))

    # 3. Semantic Qdrant Vector Retrieval + Fast LLM Audit
    violations.extend(_check_semantic_rag_violations(source_code))

    # Deduplicate violations flagging the same rule_id
    seen_rules = set()
    deduped_violations = []
    for v in violations:
        if v.rule_id not in seen_rules:
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


def audit_file(file_path: Path) -> AuditReport:
    """Read and audit a source file from disk."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    content = file_path.read_text(encoding="utf-8")
    return audit_code_content(content)


# --- 4. SARIF v2.1.0 Exporter (GitHub Code Scanning Standard) ---

def generate_sarif_report(results_by_file: dict[str, AuditReport]) -> dict:
    """Converts multi-file audit reports into standard OASIS SARIF v2.1.0 schema."""
    rules_dict = {}
    sarif_results = []

    for file_path, report in results_by_file.items():
        rel_path = os.path.relpath(file_path, start=os.getcwd()).replace("\\", "/")

        for violation in report.violations:
            rule_id = violation.rule_id
            level = "error" if violation.severity == "BLOCKING" else "warning"

            if rule_id not in rules_dict:
                rules_dict[rule_id] = {
                    "id": rule_id,
                    "name": rule_id.replace("_", " ").title().replace(" ", ""),
                    "shortDescription": {"text": violation.statute_reference},
                    "fullDescription": {"text": violation.summary},
                    "help": {
                        "text": f"Suggested remediation: {violation.suggested_fix}",
                        "markdown": f"### Statutory Requirement: {violation.statute_reference}\n\n**Issue:** {violation.summary}\n\n**Remediation:** {violation.suggested_fix}"
                    },
                    "properties": {
                        "precision": "very-high",
                        "tags": ["compliance", "ai-safety", "statutory-governance"]
                    }
                }

            sarif_results.append({
                "ruleId": rule_id,
                "level": level,
                "message": {
                    "text": f"[{violation.statute_reference}] {violation.summary} Fix: {violation.suggested_fix}"
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": rel_path,
                                "uriBaseId": "%SRCROOT%"
                            },
                            "region": {
                                "startLine": violation.line_number or 1,
                                "snippet": {
                                    "text": violation.code_snippet or ""
                                }
                            }
                        }
                    }
                ]
            })

    sarif_payload = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "AISafetyCompliance Auditor",
                        "semanticVersion": "1.0.0",
                        "informationUri": "https://github.com/laxmitesting/ai-safety",
                        "rules": list(rules_dict.values())
                    }
                },
                "results": sarif_results
            }
        ]
    }
    return sarif_payload


# --- 5. CLI Execution & GitHub CI Entrypoint ---

def main():
    parser = argparse.ArgumentParser(description="Audit source files or directories for AI statutory compliance.")
    parser.add_argument("target", help="File or directory path to audit.")
    parser.add_argument("--sarif-out", default=None, help="Optional output path to save SARIF v2.1.0 report.")
    args = parser.parse_args()

    target_path = Path(args.target)
    if not target_path.exists():
        logger.error(f"Target path does not exist: {target_path}")
        sys.exit(1)

    files_to_audit: List[Path] = []
    if target_path.is_file():
        files_to_audit.append(target_path)
    else:
        files_to_audit.extend(list(target_path.glob("**/*.py")))

    results: dict[str, AuditReport] = {}
    any_blocking = False

    print(f"\n🔍 Auditing {len(files_to_audit)} files under '{target_path}'...")
    for f in files_to_audit:
        try:
            report = audit_file(f)
            results[str(f)] = report
            if report.blocking_violations > 0:
                any_blocking = True
                print(f"❌ [BLOCKED] {f}: {report.blocking_violations} blocking violation(s)")
                for v in report.violations:
                    print(f"    - Line {v.line_number}: [{v.rule_id}] {v.summary}")
            elif report.total_violations > 0:
                print(f"⚠️  [WARNING] {f}: {report.total_violations} warning(s)")
            else:
                print(f"✅ [PASSED]  {f}")
        except Exception as e:
            logger.error(f"Error auditing {f}: {e}")

    # Generate SARIF file if requested
    if args.sarif_out:
        sarif_doc = generate_sarif_report(results)
        out_p = Path(args.sarif_out)
        out_p.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")
        print(f"\n📊 SARIF report exported to: {out_p.resolve()}")

    if any_blocking:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()