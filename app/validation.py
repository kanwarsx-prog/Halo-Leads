"""
Deterministic validation of an EvidenceBundle before persistence.

Rules applied:
- Every fact must have a source URL.
- Every source URL cited in evidence must be present in the discovered
  source list (prevents hallucinated citations).
- Every source URL must be a valid HTTP/HTTPS URL.
- Evidence items marked as "unknown" must have confidence <= 50.

For the MVP, any validation error fails the run. A later reconciliation
step may allow controlled recovery of near-valid bundles.
"""

from urllib.parse import urlparse

from app.schemas import EvidenceBundle


def validate_evidence_bundle(
    bundle: EvidenceBundle,
    known_source_urls: set[str],
) -> list[str]:
    """
    Validate an EvidenceBundle against the set of URLs discovered during
    web research.

    Validation is currently disabled per user request.
    """
    return []
