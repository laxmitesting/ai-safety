# AISafety

An automated, regulatory-first AI safety and statutory governance framework for CI/CD pipelines.

`AISafety` bridges the gap between fast-moving enterprise LLM codebases and binding statutory obligations (such as the **EU AI Act Regulation 2024/1689** and the **UK Data (Use and Access) Act 2025 s. 80 / Article 22C**). 

The platform utilizes a multi-agent architecture combining deterministic Abstract Syntax Tree (AST) static analysis, embedded vector retrieval (Qdrant), and LLM-driven fast evaluation models to intercept compliance violations before code reaches production. Audit findings are exported in standard **OASIS SARIF v2.1.0** format, rendering inline annotations directly on GitHub Pull Request diffs.

---

## Key Capabilities

* **Hybrid Audit Engine (Deterministic + Semantic RAG):**
  * **AST & Pattern Analysis:** Detects hardcoded configuration antipatterns (e.g., disabling human escalation for automated decisions) and deceptive system prompt personas (e.g., suppressing synthetic AI identity).
  * **Semantic Statutory RAG:** Queries local vector collections to align code changes against live statutory constraints.
* **SARIF v2.1.0 PR Annotations:**
  * Outputs standardized SARIF reports ingested natively by **GitHub Code Scanning**, generating line-by-line PR diff warnings, severity tags, and remediation notes.
* **Autonomous Curator Ingestion:**
  * Curates legal feeds and statutory documents into discrete, verifiable rules enforced by a token-level containment algorithm to prevent statutory hallucinations.
* **Multi-Channel Alerting & CI Automation:**
  * Blocks non-compliant PRs via automated GitHub Actions gates while dispatching alerts to Telegram and Discord.

---

## Architecture Overview

```text
[Phase 1: Ingestion, Distillation & HITL Gate]
      +-------------------------------+
      | Official Legal Sources        |
      | (legislation.gov.uk / EUR-Lex)|
      +-------------------------------+
                     |
                     v
      +-------------------------------+
      |         Curator Agent         |
      |   (LLM Distillation Model)    |
      +-------------------------------+
                     |
                     v
      +-------------------------------+
      |  Groundedness Gate (>= 85%)   | ----(Fail)----> [ Discard Hallucination ]
      +-------------------------------+
                     | (Pass)
                     v
      +-------------------------------+
      | memory/pending_proposals.yaml |
      +-------------------------------+
                     |
                     v [HITL Review: promote_rule.py]
      +-------------------------------+
      |   Embedded Qdrant Vector DB   |
      | (statutory_rules Collection)  |
      +-------------------------------+
                     |
  . . . . . . . . . .|. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
  . [Phase 2: CI/CD PR Governance & Active Learning]                            .
  .                                                                             .
  .   +-------------------------------+                                         .
  .   |   PR Diffs / Untrusted Code   |                                         .
  .   +-------------------------------+                                         .
  .                  |                                                          .
  .                  v                                                          .
  .   +-------------------------------+                                         .
  .   |        audit_system.py        |                                         .
  .   +-------------------------------+                                         .
  .                  |                                                          .
  .                  v                                                          .
  .   +-----------------------------------------+                               .
  .   |              Auditor Agent              |<..(Query Top-K Constraints)...'
  .   |   (AST Parser + Regex + Semantic RAG)   |
  .   +-----------------------------------------+
                     |
                     +----------------------------+
                     |                            |
       (Exit 0: Compliant)           (Exit 1: Violations Found)
                     |                            |
                     v                            v
      +-------------------------------+  +-------------------------------------+
      |    GitHub PR Passes Green     |  | GitHub PR Blocked + SARIF Annotate  |
      |      (Approved to Merge)      |  | Dispatch Telegram Alert             |
      +-------------------------------+  +-------------------------------------+
                                                  |
                                                  v
                                       +-------------------------------------+
                                       |           Trace Harvester           |
                                       |  (evals/benchmarks/pending_evals)   |
                                       +-------------------------------------+
                                                  |
                                                  v [Weekly Curation]
                                       +-------------------------------------+
                                       | Active Benchmark Suites (Eval Sets) |
                                       +-------------------------------------+
```

---
## Documentation

Detailed architectural specifications, regulatory mappings, and benchmark methodology are available in the [`docs/`](docs/) directory:

* [System Architecture](docs/architecture.md) – End-to-end component interactions, embedding pipelines, and CI/CD runtime design.
* [Statutory Mapping](docs/statutory_mapping.md) – Cross-jurisdictional legal taxonomy (EU AI Act Art. 50, UK DUAA 2025 s. 80 / Art. 22C GDPR).
* [Evaluation & Harvesting](docs/evals.md) – Groundedness thresholds, recall/precision benchmarks, and the active learning CI telemetry pipeline.
* [Decision Tree](docs/decision_tree.md) – CI/CD gating logic, statutory severity thresholds (BLOCKING vs. WARNING), authorized waiver protocols, and automated remediation reporting.

## Directory Structure

```text
├── .env                               # Environment secrets (API keys, webhooks)
├── .gitignore                         # Git exclusion rules
├── README.md                          # Framework overview and quickstart
├── report.sarif                       # Exported OASIS SARIF v2.1.0 audit log
├── requirements.txt                   # Pinned project runtime dependencies
├── .github/
│   └── workflows/
│       ├── ai_compliance_check.yaml    # PR compliance gate & SARIF upload
│       ├── ci.yaml                     # Automated test suite
        ├── promote-statutory-rule.yaml # HITL workflow_dispatch trigger to promote vetted proposals to Qdrant registry
│       └── scheduled_feed_radar.yaml   # Scheduled regulatory feed tracking
├── configs/
    ├── regulatory_registry.yaml       # Authoritative statutory feeds & rule mapping sources
│   └── settings.py                    # Global models, paths, and thresholds
├── docs/
│   ├── ARCHITECTURE.md                # System design & component interaction
│   ├── DECISION_TREE.md               # Audit routing & escalation flowcharts
│   ├── EVALS_AND_HARVESTING.md        # Verification benchmarks & statutory scraping
│   └── STATUTORY_MAPPING.md           # Legal requirements to code rule schemas
└── evals/
    ├── benchmarks/
    │   ├── automated_decisions.jsonl
    │   ├── deceptive_prompts.jsonl
    │   └── pending_evals.jsonl
    ├── eval_auditor_recall.py
    └── eval_curator_groundedness.py
├── examples/
│   ├── pr_compliant_pipeline.py       # Valid human-in-the-loop implementation
│   ├── pr_violation_deceptive_prompt.py # Breaches EU AI Act Art. 50(1)
│   └── pr_violation_duaa_adm.py       # Breaches UK DUAA s. 80 / Art. 22C
├── memory/
│   ├── pending_proposals.yaml         # Staged rule revisions awaiting human sign-off
│   ├── qdrant/                        # Local embedded vector store
│   │   └── collection/statutory_rules/
│   │       ├── .lock
│   │       ├── meta.json
│   │       └── storage.sqlite
│   └── statutory_cache/               # Ground-truth raw legal source text
│       ├── eu_ai_act_core.txt
│       └── uk_duaa_adm_rules.txt
├── src/
    ├── audit_system.py                # CLI audit entrypoint
│   ├── agents/
│   │   ├── auditor.py                 # Hybrid code auditor & SARIF exporter
│   │   └── curator.py                 # Statutory text ingestion & distillation
│   └── tools/
│       ├── feed_discovery.py          # Regulatory feed crawler & tracker[cite: 5]
│       ├── harvester.py               # CI failure trace deduplication & capture[cite: 5]
│       ├── legislation.py             # Statute fetcher & XML parsing utilities[cite: 5]
│       ├── notifications.py           # Telegram & Discord webhook dispatchers[cite: 5]
│       ├── promote_rule.py            # Staged proposal promotion script[cite: 5]
│       └── qdrant_client.py           # Embedded vector store & embedding singleton[cite: 5]
└── tests/
    ├── test_auditor_examples.py       # End-to-end fixture assertion suite[cite: 5]
    ├── test_legislation_tool.py       # Statutory fetching & XML parsing tests[cite: 5]
    └── test_notifications.py          # Alert webhook delivery mock tests[cite: 5]
```

---

## Getting Started

### 1. Prerequisites

* **Python 3.12+**
* An **OpenAI API Key** (for fast semantic auditor checks and statutory distillation)

### 2. Installation

Clone the repository and install the dependencies in a virtual environment:

```bash
git clone [https://github.com/laxmitesting/ai-safety.git](https://github.com/laxmitesting/ai-safety.git)
cd ai-safety

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the root directory:

```bash
OPENAI_API_KEY="your-openai-api-key"
TELEGRAM_BOT_TOKEN="your-telegram-bot-token" # Optional
TELEGRAM_CHAT_ID="your-telegram-chat-id"     # Optional
DISCORD_WEBHOOK_URL="your-discord-webhook"   # Optional
```

---

## Usage

### Indexing Regulations (Curator Agent)

Distill raw legal statutes from `memory/statutory_cache/`, apply token-overlap verification, and index grounded rules into local vector storage:

```bash
python -m src.agents.curator
```

### Running the Compliance Audit

Audit a file or entire directory for statutory breaches and generate an OASIS SARIF report:

```bash
# Audit the examples directory
python -m src.agents.auditor examples/ --sarif-out report.sarif

# Audit a specific script
python -m src.agents.auditor examples/pr_violation_deceptive_prompt.py --sarif-out report.sarif
```

If blocking violations are encountered, the process exits with status code `1`, halting downstream CI deployment steps.

---

## CI/CD & GitHub Code Scanning

When integrated into GitHub Actions, the generated `report.sarif` surfaces findings directly inside pull requests.

```yaml
# .github/workflows/ai_compliance_check.yaml snippet
- name: Run Hybrid Compliance Auditor
  run: python -m src.agents.auditor examples/ --sarif-out report.sarif

- name: Upload SARIF to GitHub Code Scanning
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: report.sarif
    category: statutory-compliance
```

Violations are displayed inline under the **Files Changed** diff view with legal citations and concrete fix instructions:

```text
🔴 [EU AI Act Reg 2024/1689 Art. 50(1)] System prompt explicitly instructs AI to conceal its identity or pretend to be human.
Fix: Ensure the system persona discloses synthetic nature to natural persons.
```

---

## Running Tests

Run the unit test suite and evaluate detector performance:

```bash
pytest -v
```

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.