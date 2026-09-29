"""src/config.py: Central configuration and environment defaults."""

import os
from pathlib import Path
from dotenv import load_dotenv

# --- Base Directory Paths ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

CONFIGS_DIR = PROJECT_ROOT / "configs"
REGISTRY_PATH = CONFIGS_DIR / "regulatory_registry.yaml"

MEMORY_DIR = PROJECT_ROOT / "memory"
CACHE_DIR = MEMORY_DIR / "statutory_cache"
QDRANT_STORAGE_DIR = MEMORY_DIR / "qdrant"

# --- Evaluation & Benchmarks Paths ---
EVALS_DIR = PROJECT_ROOT / "evals"
BENCHMARKS_DIR = EVALS_DIR / "benchmarks"
PENDING_EVALS_PATH = BENCHMARKS_DIR / "pending_evals.jsonl"
AUTOMATED_DECISIONS_BENCHMARK = BENCHMARKS_DIR / "automated_decisions.jsonl"
DECEPTIVE_PROMPTS_BENCHMARK = BENCHMARKS_DIR / "deceptive_prompts.jsonl"

# LLM & Embedding Specs
# Defaulting to OpenAI models, overridable via environment variables in CI/CD
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CURATOR_MODEL = os.getenv("CURATOR_MODEL", "gpt-5.5")         # Heavyweight extraction
AUDITOR_MODEL = os.getenv("AUDITOR_MODEL", "gpt-5.4-mini")    # Fast PR gatekeeping
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

# Evaluation & Safety Thresholds
GROUNDEDNESS_THRESHOLD = float(os.getenv("GROUNDEDNESS_THRESHOLD", "0.85"))
RECALL_TARGET = float(os.getenv("RECALL_TARGET", "0.95"))

# --- External Notification Channels ---
# High-priority CI/CD Auditor blocking alerts
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Low-priority / Async Statutory Radar updates
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")