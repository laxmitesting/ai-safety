"""test_legislation_tool.py: Tests for statutory fetching and caching via YAML registry."""

import pytest
from pathlib import Path
from unittest.mock import patch
from src.tools.legislation import fetch_statutory_text, CACHE_DIR, clean_markup


def test_clean_markup_strips_tags_and_normalizes_whitespace():
    """Verify that XML/HTML tags and erratic whitespaces are removed cleanly."""
    raw_snippet = "<div><leg:title>Data (Use and Access) Act</leg:title>\n\n  <p>Section 80</p></div>"
    cleaned = clean_markup(raw_snippet)
    assert cleaned == "Data (Use and Access) Act Section 80"
    assert "<" not in cleaned and ">" not in cleaned


@pytest.mark.asyncio
async def test_fetch_unknown_topic():
    """Verify safe fallback message when requesting an unknown key."""
    result = await fetch_statutory_text("non_existent_key")
    assert "Error: Unknown topic" in result


@pytest.mark.asyncio
async def test_fetch_uk_duaa_adm_rules():
    """Verify live fetch and local snapshot caching for UK DUAA 2025 Section 80."""
    result = await fetch_statutory_text("uk_duaa_adm_rules", max_chars=1200)

    assert not result.startswith("Error")
    assert len(result) >= 250
    cached_file = CACHE_DIR / "uk_duaa_adm_rules.txt"
    assert cached_file.exists()
    assert cached_file.read_text(encoding="utf-8") == result


@pytest.mark.asyncio
async def test_fetch_eu_cellar_ai_act():
    """Verify live fetch and local caching for EU AI Act via direct CELLAR resource."""
    result = await fetch_statutory_text("eu_ai_act_core", max_chars=1200)

    assert not result.startswith("Error")
    assert len(result) >= 250
    assert any(term in result.lower() for term in ["regulation", "artificial intelligence", "union"])

    cached_file = CACHE_DIR / "eu_ai_act_core.txt"
    assert cached_file.exists()


@pytest.mark.asyncio
async def test_fetch_statutory_text_cache_fallback():
    """Verify system gracefully falls back to local snapshot if network fails."""
    mock_topic = "test_statutory_topic"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fallback_file = CACHE_DIR / f"{mock_topic}.txt"
    fallback_content = "Pre-cached statutory text for emergency fallback operations."
    fallback_file.write_text(fallback_content, encoding="utf-8")

    mock_registry = {
        mock_topic: {"url": "https://mock.invalid/endpoint", "jurisdiction": "UK"}
    }

    # Patch load_regulatory_registry 
    with patch("src.tools.legislation.load_regulatory_registry", return_value=mock_registry):
        with patch("src.tools.legislation.fetch_with_retry", side_effect=RuntimeError("Simulated Network Drop")):
            result = await fetch_statutory_text(mock_topic)
            assert result == fallback_content

    if fallback_file.exists():
        fallback_file.unlink()