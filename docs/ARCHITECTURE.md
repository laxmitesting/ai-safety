# System Architecture & Technical Specifications

`ai-safety` is an automated compliance and safety gatekeeper that enforces statutory constraints—specifically **UK DUAA 2025 s. 80** and the **EU AI Act (Regulation 2024/1689)**—directly inside CI/CD developer pipelines.

---

## 1. High-Level System Topology

The platform decouples legal ingestion and distillation from code-level policy enforcement via an **Agentic Retrieval-Augmented Generation (RAG)** pipeline backed by Qdrant.

```mermaid
flowchart TD
    %% ==========================================
    %% PHASE 1: DISCOVERY & STATUTORY INGESTION
    %% ==========================================
    subgraph Phase1["1. Initial Discovery & Statutory Ingestion (Pre-CI / Offline Registry)"]
        direction TB
        L1["legislation.gov.uk API<br/>(UK DUAA 2025 s. 80 / Art 22C)"] --> LT[Legislation Fetcher Tool]
        L2["EUR-Lex Official Journals<br/>(EU AI Act Reg 2024/1689)"] --> LT
        
        LT -->|Raw XML / Text| CR[Curator Agent]
        
        CR -->|Token Containment Check| G{Groundedness<br/>Ratio ≥ 0.85?}
        G -->|No: Hallucinated / Distorted| REJ[Reject Rule Ingestion]
        G -->|Yes: Ground-Truth Verified| DR[Generate DistilledRule Schema]
        
        DR --> EMB[FastEmbed / Dense Embedder]
        EMB -->|Upsert Vectors & Payloads| QD[(Qdrant Vector Store<br/>statutory_rules Collection)]
    end

    %% ==========================================
    %% PHASE 2: PR GOVERNANCE & TELEMETRY
    %% ==========================================
    subgraph Phase2["2. Developer CI/CD Governance & Active Learning (Online Gatekeeper)"]
        direction TB
        PR[Developer Submits Pull Request] --> AUD[src/audit_system.py]
        
        AUD --> AG[Auditor Agent]
        
        %% RAG Retrieval Link from Qdrant
        QD -.->|Semantic Query: Top-K Directives & Citations| AG
        
        AG --> CHK{Statutory Audit Check}
        
        CHK -->|Blocking Violations Found| BLK[Exit Code 1: Block Merge]
        CHK -->|Compliant / Clean| PASS[Exit Code 0: Approve Merge]
        
        BLK --> CMT[Post Remediation Comment to GitHub PR]
        BLK --> HARV[Trace Harvester]
        PASS -.->|If Contested or Exemption Active| HARV
        
        HARV --> STG[(evals/benchmarks/pending_evals.jsonl)]
        STG -->|Human-in-the-Loop Labeling| BENCH[Active Benchmark Evaluation Sets]
    end

    %% Explicit connection from Discovery phase to Runtime phase
    Phase1 ==>|Populates Vector Knowledge Base| Phase2
  ```

---

## 2. Core Subsystems & Component Contracts

### 2.1 The Curator Agent (`src/agents/curator.py`)
Transforms opaque statutory text into enforceable technical rules, preventing legal hallucination through token-level containment.

* **Schema Guarantee (`DistilledRule`):**
  * `rule_id`: Stable snake_case identifier (e.g., `uk_duaa_human_intervention`).
  * `statute_reference`: Statutory citation (e.g., `DUAA 2025 c. 18 s. 80 (Art 22C)`).
  * `verbatim_quote`: Exact excerpt extracted from source legislation.
  * `enforceable_constraint`: Operational rule checked during PR audits.
  * `trigger_domain`: Scope of application (`employment_screening`, `credit_scoring`, `biometrics`, `general_adm`).
* **Hallucination Guardrail (Groundedness Check >= 85%):** Verifies that at least 85% of the unique words in the Curator's extracted quote exist verbatim inside the raw statutory text downloaded from legislation.gov.uk. This prevents the system from storing hallucinated legal requirements or phantom clauses in Qdrant, while tolerating minor formatting, punctuation, and whitespace differences.

---

### 2.2 Memory & Vector Storage Subsystem (`src/tools/qdrant_client.py`)
Maintains vector memory to decouple rule evolution from code releases.

* **Collection Schema (`statutory_rules`):**
  * **Vector:** 384-dimensional dense embedding of `enforceable_constraint` (Cosine distance).
  * **Payload:**
    ```json
    {
      "rule_id": "uk_duaa_s80_meaningful_human",
      "statute_reference": "DUAA 2025 c. 18 s. 80 (Art 22C)",
      "jurisdiction": "UK",
      "verbatim_quote": "A decision is solely automated if there is no meaningful human involvement...",
      "enforceable_constraint": "Require HumanInterventionHook in solely automated decision flows.",
      "trigger_domain": "general_adm",
      "status": "ACTIVE"
    }
    ```
* **Storage Modes:** Supports `:memory:` (zero-dependency for fast CI execution and tests) and persistent disk/network storage for production registries.

---

### 2.3 The Auditor Agent (`src/agents/auditor.py`)
Executes a **Hybrid Verification Model** combining fast deterministic checks with semantic RAG retrieval:

1. **Deterministic Static Analysis (AST & Syntax):** 
   Catches explicit syntax violations (e.g., `'human_escalation_available': False`) with zero latency.
2. **Semantic RAG Audit (Qdrant-Assisted):**
   * Chunks modified system prompts, docstrings, and scoring logic.
   * Embeds chunks and queries the `statutory_rules` Qdrant collection for nearest statutory mandates.
   * Assesses whether the candidate code/prompt bypasses or violates the retrieved mandate (e.g., deceptive personas, subtle deflection of synthetic identity).

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer / CI Runner
    participant CLI as src/audit_system.py
    participant Audit as src/agents/auditor.py
    participant Qdrant as Qdrant Vector Store
    participant Harv as src/tools/harvester.py
    participant GH as GitHub PR API

    Dev->>CLI: python src/audit_system.py examples/
    CLI->>Audit: audit_file(path)
    Audit->>Audit: Extract AST tokens & system prompts
    Audit->>Qdrant: Query nearest constraints (Embeddings)
    Qdrant-->>Audit: Top-K statutory payloads (Art. 50 / Art. 22C)
    Audit->>Audit: Evaluate code against retrieved mandates
    
    alt Statutory Violation Flagged
        Audit-->>CLI: AuditReport(status=FAILED, violations=[...])
        CLI->>Harv: harvest_trace(file, report)
        Harv-->>CLI: Appended to pending_evals.jsonl
        CLI->>GH: Post PR comment with statutory reference & remediation
        CLI-->>Dev: Exit Code 1 (Merge Blocked)
    else Compliant Pipeline
        Audit-->>CLI: AuditReport(status=PASSED, violations=[])
        CLI-->>Dev: Exit Code 0 (Merge Approved)
    end
```

---

### 2.4 Active Learning Trace Harvester (`src/tools/harvester.py`)
Provides automated telemetry and passive dataset curation by intercepting audit events during CI execution.

* **Component Responsibility:** Serializes unhandled edge cases, statutory violations, and override waivers into an append-only JSONL buffer (`evals/benchmarks/pending_evals.jsonl`).
* **Deduplication Key:** Computes a SHA-256 hash over whitespace-normalized code chunks to enforce idempotent logging across repeated CI retries.
* **Payload Contract:**
  ```json
  {
    "fingerprint": "sha256_hash",
    "timestamp": "2026-09-25T11:00:00Z",
    "source_file": "examples/pr_violation_duaa_adm.py",
    "status": "FAILED",
    "rule_id": "uk_duaa_s80_art22c_adm",
    "code_snippet": "'human_escalation_available': False",
    "override_reason": ""
  }
  ```
  * **Operational Workflow:** For waiver triage criteria and the promotion lifecycle into regression suites, see DECISION_TREE.md.

---

## 3. Statutory Mapping Matrix

| Jurisdiction | Statute | Technical Requirement | Auditor Enforcement |
| :--- | :--- | :--- | :--- |
| **United Kingdom** | **UK DUAA 2025 s. 80**<br>(Articles 22A–22D UK GDPR) | Mandatory contestability and right to human intervention for solely automated decisions. | Flags absence of `route_for_human_review` or explicit `human_escalation_available: False`. |
| **European Union** | **EU AI Act Reg 2024/1689**<br>(Article 50 Transparency) | AI systems interacting with natural persons must disclose their synthetic identity. | Flags system prompt instructions directing the agent to impersonate human workers or deny being an AI. |
| **European Union** | **EU AI Act Reg 2024/1689**<br>(Annex III High-Risk Systems) | High-risk employment and credit-scoring models require active human oversight mechanisms (Art. 14). | Requires explicit review escalation thresholds on predictive scoring endpoints. |