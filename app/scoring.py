"""
Deterministic lead scoring.

Weights:
  itsm_confidence        15%  — is a legacy ITSM tool actually used here?
  basic_use_likelihood   25%  — is usage narrow / basic rather than enterprise-wide?
  cost_pressure          20%  — cost-reduction or vendor-consolidation pressure?
  renewal_proximity      20%  — contract renewal or review coming up?
  migration_fit          20%  — would migration be straightforward?

Priority bands:
  >= 80  immediate_pursuit
  >= 65  research_and_nurture
  >= 45  monitor
  < 45   do_not_pursue

Pursuit gate:
  Unverified ITSM status hard-caps score to <= 44 regardless of other signals.
  "Possible" status prevents immediate_pursuit — capped to research_and_nurture.
"""

from dataclasses import dataclass


SCORING_VERSION = "v1"


@dataclass(frozen=True)
class ScoreResult:
    overall_score: int
    priority: str


def calculate_lead_score(
    *,
    itsm_confidence: int,
    basic_use_likelihood: int,
    cost_pressure: int,
    renewal_proximity: int,
    migration_fit: int,
) -> ScoreResult:
    """
    Calculate a weighted lead score from five component scores (0–100 each).

    Raises ValueError if any component is outside [0, 100].
    """
    values = {
        "itsm_confidence": itsm_confidence,
        "basic_use_likelihood": basic_use_likelihood,
        "cost_pressure": cost_pressure,
        "renewal_proximity": renewal_proximity,
        "migration_fit": migration_fit,
    }

    for name, value in values.items():
        if not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100, got {value}")

    score = round(
        itsm_confidence * 0.15
        + basic_use_likelihood * 0.25
        + cost_pressure * 0.20
        + renewal_proximity * 0.20
        + migration_fit * 0.20
    )

    if score >= 80:
        priority = "immediate_pursuit"
    elif score >= 65:
        priority = "research_and_nurture"
    elif score >= 45:
        priority = "monitor"
    else:
        priority = "do_not_pursue"

    return ScoreResult(
        overall_score=score,
        priority=priority,
    )


def apply_pursuit_gate(
    *,
    overall_score: int,
    priority: str,
    itsm_status: str,
) -> tuple[int, str, str]:
    """
    Apply the ITSM-verification pursuit gate.

    Unverified accounts must never be recommended for immediate or nurture
    pursuit regardless of how other signals score.
    """
    if itsm_status == "unverified":
        return min(overall_score, 44), "do_not_pursue", "hard_cap_unverified"

    if itsm_status == "possible" and priority == "immediate_pursuit":
        return min(overall_score, 79), "research_and_nurture", "cap_possible_status"

    return overall_score, priority, "pass"
