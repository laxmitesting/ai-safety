"""audit_system.py: CLI and CI/CD entry point for statutory code audits."""

import argparse
import sys
from pathlib import Path
from typing import List


# Ensure repository root is on sys.path even when invoked directly as a script
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Internal package imports follow
from src.agents.auditor import audit_file, AuditReport
from src.tools.harvester import harvest_trace
from configs.settings import PROJECT_ROOT

def format_cli_report(file_path: Path, report: AuditReport) -> str:
    """Format an audit report into clear terminal output."""
    lines = []
    lines.append(f"\nEvaluating: {file_path.name}")
    lines.append("=" * 70)
    lines.append(f"Result: {report.status} (Blocking: {report.blocking_violations}, Total: {report.total_violations})")

    if report.violations:
        lines.append("\nDetected Statutory Violations:")
        for idx, v in enumerate(report.violations, 1):
            lines.append(f"  {idx}. [{v.severity}] {v.rule_id}")
            lines.append(f"     Statute: {v.statute_reference}")
            lines.append(f"     Issue:   {v.summary}")
            if v.code_snippet:
                lines.append(f"     Snippet: {v.code_snippet}")
            lines.append(f"     Fix:     {v.suggested_fix}")
    else:
        lines.append("  No statutory violations detected. Compliant with active registry.")

    lines.append("=" * 70)
    return "\n".join(lines)


def run_audit(
    paths: List[Path],
    override_reason: str = "",
    enable_harvest: bool = True,
) -> int:
    """Run audit across files, harvest traces, and return standard exit code."""
    has_blocking_failure = False

    for target_path in paths:
        if not target_path.exists():
            print(f"Error: Path does not exist: {target_path}", file=sys.stderr)
            continue

        files_to_check = [target_path] if target_path.is_file() else list(target_path.glob("**/*.py"))

        for file in files_to_check:
            report = audit_file(file)
            print(format_cli_report(file, report))

            # Harvest trace into pending_evals.jsonl if informative
            if enable_harvest:
                raw_text = file.read_text(encoding="utf-8")
                harvested = harvest_trace(
                    source_file=str(file),
                    raw_content=raw_text,
                    audit_report=report.model_dump(),
                    user_override=bool(override_reason),
                    override_reason=override_reason or None,
                )
                if harvested:
                    print(f"  [Harvester] Logged edge case to evals/benchmarks/pending_evals.jsonl")

            if report.status == "FAILED" and not override_reason:
                has_blocking_failure = True

    if override_reason:
        print(f"\n⚠️  PR Override Active: Bypassing gatekeeper failure. Reason: '{override_reason}'")
        return 0

    return 1 if has_blocking_failure else 0


def main():
    parser = argparse.ArgumentParser(description="AISafetyCompliance / ai-safety PR statutory compliance checker.")
    parser.add_argument("paths", nargs="+", type=Path, help="Python source files or directories to audit")
    parser.add_argument("--override-reason", default="", help="Provide an audit override reason to bypass blocking in CI")
    parser.add_argument("--no-harvest", action="store_true", help="Disable telemetry logging to pending benchmarks")

    args = parser.parse_args()
    exit_code = run_audit(
        paths=args.paths,
        override_reason=args.override_reason,
        enable_harvest=not args.no_harvest,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()