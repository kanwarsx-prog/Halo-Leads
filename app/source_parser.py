"""
Defensively parse source URLs out of a raw OpenAI Responses API payload.

The response structure may evolve across model versions, so this module
walks the entire JSON tree and collects any dict that contains a valid
HTTP/HTTPS URL. Deduplication is by URL string. The raw JSON is stored
alongside the parsed URL so that more precise parsing can be added later
without rerunning research.
"""

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse


def walk_json(value: Any) -> Iterable[Any]:
    """Recursively yield every value in a JSON structure."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def collect_sources(raw_response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Walk the full raw response and collect unique HTTP/HTTPS URLs.

    Returns a list of dicts with keys: url, title, domain, raw_metadata.
    Deduplication is by URL string; the first occurrence wins.
    """
    discovered: dict[str, dict[str, Any]] = {}

    for item in walk_json(raw_response):
        if not isinstance(item, dict):
            continue

        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue

        parsed = urlparse(url)
        title = item.get("title")

        if url not in discovered:
            discovered[url] = {
                "url": url,
                "title": title if isinstance(title, str) else None,
                "domain": parsed.netloc.lower(),
                "raw_metadata": item,
            }

    return list(discovered.values())
