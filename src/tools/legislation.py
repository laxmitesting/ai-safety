"""legislation.py: Ingestion tool for sovereign statutory endpoints with dynamic registry support."""

import asyncio
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

import httpx
import yaml

# Import centralized paths directly from your settings configuration
from configs.settings import CACHE_DIR, REGISTRY_PATH

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Accept": "application/xhtml+xml, application/xml, text/xml, text/html;q=0.9",
    "Accept-Language": "en",
    "User-Agent": "AISafetyComplianceChecker/2026.1",
}


def load_registry(registry_path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    """Load canonical regulatory registry with safety defaults."""
    if not registry_path.exists():
        raise FileNotFoundError(f"Regulatory registry not found at: {registry_path}")
    with open(registry_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", {})


def resolve_source_target(source_key: str, registry: Dict[str, Any]) -> tuple[str, Optional[str]]:
    """Resolve the effective download URL and the canonical cache identifier.

    Handles direct URLs, parent inheritance, and arbitrary registry inserts.
    """
    if source_key not in registry:
        raise KeyError(f"Statutory source '{source_key}' not registered in {REGISTRY_PATH.name}")

    entry = registry[source_key]
    url = entry.get("url")
    parent_key = entry.get("parent_source")

    # If this is a child or sliced entry referencing a parent source
    if not url and parent_key:
        if parent_key not in registry:
            raise ValueError(f"Source '{source_key}' references non-existent parent '{parent_key}'")
        parent_url = registry[parent_key].get("url")
        if not parent_url:
            raise ValueError(f"Parent source '{parent_key}' does not define a direct 'url'")
        return parent_url, parent_key

    if not url:
        raise ValueError(f"Registry entry '{source_key}' lacks a valid 'url' or 'parent_source'")

    return url, None


def fetch_statutory_text(
    source_key: str,
    force_refresh: bool = False,
    registry_path: Path = REGISTRY_PATH,
) -> str:
    """Fetch and cache statutory prose for any source entry in the registry.

    Reuses parent cache if source is a derivative, avoiding redundant multi-MB downloads.
    """
    registry = load_registry(registry_path)
    url, parent_key = resolve_source_target(source_key, registry)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # If child has a parent, check parent cache first
    effective_cache_key = parent_key if parent_key else source_key
    cache_path = CACHE_DIR / f"{effective_cache_key}.txt"

    if cache_path.exists() and not force_refresh:
        return cache_path.read_text(encoding="utf-8")

    # Download from statutory authority endpoint
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers=DEFAULT_HEADERS)
            response.raise_for_status()
            raw_text = response.text
    except httpx.HTTPError as exc:
        logger.error(f"Failed fetching statutory text from {url}: {exc}")
        raise

    cache_path.write_text(raw_text, encoding="utf-8")
    return raw_text


def discover_feed_updates(feed_source_key: str) -> List[Dict[str, str]]:
    """Parse an XML discovery feed (e.g., legislation.gov.uk contents/Atom feed)

    Returns newly published instruments, sections, or amendments.
    """
    raw_xml = fetch_statutory_text(feed_source_key)
    updates = []

    try:
        root = ET.fromstring(raw_xml)
        # Handle Atom/XML feed structures dynamically
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", namespaces) or root.findall("entry")

        for item in entries:
            title_el = item.find("atom:title", namespaces) or item.find("title")
            link_el = item.find("atom:link", namespaces) or item.find("link")

            title = title_el.text.strip() if title_el is not None and title_el.text else "Untitled Amendment"
            href = link_el.attrib.get("href") if link_el is not None else ""

            if href:
                updates.append({"title": title, "url": href})
    except ET.ParseError:
        # If feed is regular HTML or plaintext rather than pure XML
        logger.warning(f"Source '{feed_source_key}' is not standard XML. Returning raw snippet.")

    return updates