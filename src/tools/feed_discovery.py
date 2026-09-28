"""feed_discovery.py: Automated radar scanning statutory feeds and official gazettes for amendments."""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

import httpx
import yaml

from configs.settings import CACHE_DIR, REGISTRY_PATH
from src.tools.notifications import send_discord_alert

logger = logging.getLogger("feed_discovery")
logging.basicConfig(level=logging.INFO)

HEADERS = {
    "User-Agent": "AISafetyComplianceRadar/2026.1",
    "Accept": "application/atom+xml, application/rss+xml, text/xml, application/xml",
}


def load_regulatory_registry() -> Dict[str, Any]:
    """Reads the static registry YAML defining tracked statutes and feed URLs."""
    if not REGISTRY_PATH.exists():
        logger.error(f"Regulatory registry file missing at: {REGISTRY_PATH}")
        return {}
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def fetch_feed_xml(url: str) -> Optional[ET.Element]:
    """Downloads and parses an Atom or RSS XML feed."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            return ET.fromstring(resp.text)
        except (httpx.HTTPError, ET.ParseError) as exc:
            logger.error(f"Failed to fetch or parse feed from {url}: {exc}")
            return None


def extract_feed_entries(root: ET.Element) -> List[Dict[str, str]]:
    """Extracts entry metadata from Atom or RSS feed trees."""
    entries = []
    # Strip namespaces for unified querying
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    # Handle standard RSS items
    for item in root.findall(".//item"):
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        pub_date = item.findtext("pubDate", default="").strip()
        if title:
            entries.append({"title": title, "link": link, "updated": pub_date})

    # Handle Atom entries
    for entry in root.findall(".//entry"):
        title = entry.findtext("title", default="").strip()
        link_elem = entry.find("link")
        link = link_elem.get("href", "").strip() if link_elem is not None else ""
        updated = entry.findtext("updated", default="").strip()
        if title:
            entries.append({"title": title, "link": link, "updated": updated})

    return entries


async def check_statutory_source(source_key: str, source_cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    """Evaluates a single regulatory feed for newly published legislative instruments."""
    feed_url = source_cfg.get("feed_url")
    if not feed_url:
        return []

    logger.info(f"Scanning radar for [{source_key}] at {feed_url}...")
    root = await fetch_feed_xml(feed_url)
    if root is None:
        return []

    entries = extract_feed_entries(root)
    keywords = [kw.lower() for kw in source_cfg.get("keywords", [])]

    matched_updates = []
    for item in entries:
        title_lower = item["title"].lower()
        if any(kw in title_lower for kw in keywords):
            matched_updates.append(item)

    return matched_updates


async def run_discovery_cycle() -> None:
    """Executes a full discovery cycle across all entries in regulatory_registry.yml."""
    registry = load_regulatory_registry()
    sources = registry.get("sources", {})

    if not sources:
        logger.warning("No regulatory sources configured in registry. Skipping cycle.")
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    all_alerts = []

    for key, cfg in sources.items():
        updates = await check_statutory_source(key, cfg)
    for update in updates:
        msg = f"New statutory instrument or amendment detected: **{update['title']}**\n[View Publication]({update['link']})"
        logger.info(f"Radar Alert [{key}]: {update['title']}")

        # Dispatch exclusively to Discord channel
        await send_discord_alert(
            title=f"Regulatory Radar Alert: {key.upper()}",
            message=msg,
            rule_id=key,
        )

    logger.info(f"Discovery radar cycle completed. Detected {len(all_alerts)} relevant items.")


if __name__ == "__main__":
    asyncio.run(run_discovery_cycle())