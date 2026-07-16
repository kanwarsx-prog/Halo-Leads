from app.source_parser import collect_sources


def test_collect_sources_deduplicates_urls() -> None:
    """The same URL appearing twice should produce only one source entry."""
    payload = {
        "output": [
            {
                "type": "message",
                "annotations": [
                    {
                        "url": "https://example.com/a",
                        "title": "Example A",
                    },
                    {
                        "url": "https://example.com/a",
                        "title": "Example A duplicate",
                    },
                ],
            }
        ]
    }

    sources = collect_sources(payload)

    assert len(sources) == 1
    assert sources[0]["url"] == "https://example.com/a"


def test_collect_sources_ignores_non_http() -> None:
    """Non-HTTP URLs (e.g. mailto:, ftp:) should be ignored."""
    payload = {
        "results": [
            {"url": "mailto:test@example.com"},
            {"url": "ftp://files.example.com/doc.pdf"},
            {"url": "https://valid.example.com/page"},
        ]
    }

    sources = collect_sources(payload)

    assert len(sources) == 1
    assert sources[0]["url"] == "https://valid.example.com/page"


def test_collect_sources_extracts_domain() -> None:
    """domain field should be the netloc of the URL, lowercased."""
    payload = {"items": [{"url": "https://WWW.ServiceNow.COM/customers/example"}]}

    sources = collect_sources(payload)

    assert len(sources) == 1
    assert sources[0]["domain"] == "www.servicenow.com"


def test_collect_sources_handles_nested_structure() -> None:
    """URLs nested arbitrarily deep in the JSON should be found."""
    payload = {
        "level1": {
            "level2": {
                "level3": [
                    {"url": "https://deep.example.com/nested", "title": "Deep"},
                ]
            }
        }
    }

    sources = collect_sources(payload)

    assert len(sources) == 1
    assert sources[0]["url"] == "https://deep.example.com/nested"
    assert sources[0]["title"] == "Deep"


def test_collect_sources_empty_response() -> None:
    """Empty response should return an empty list."""
    assert collect_sources({}) == []


def test_collect_sources_multiple_urls() -> None:
    """Multiple distinct URLs should all be returned."""
    payload = {
        "results": [
            {"url": "https://example.com/a"},
            {"url": "https://example.com/b"},
            {"url": "https://example.com/c"},
        ]
    }

    sources = collect_sources(payload)

    urls = {s["url"] for s in sources}
    assert urls == {
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    }
