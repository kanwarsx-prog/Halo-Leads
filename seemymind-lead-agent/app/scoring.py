from dataclasses import dataclass

SCORING_VERSION = "smm-v1"


@dataclass(frozen=True)
class SchoolScoreResult:
    overall_score: int
    priority: str


def calculate_school_score(
    *,
    need_score: int,
    fit_score: int,
    named_senco_found: bool,
    is_part_of_mat: bool,
    has_ofsted_quote: bool,
    sen_percentage: float | None = 0.0,
) -> SchoolScoreResult:
    """
    Calculate an evidence-grounded priority score (0-100) for a UK school or trust.
    """
    # Base need score adjusted by statutory SEN percentage if known (>16% is above UK average)
    adjusted_need = need_score
    if sen_percentage and sen_percentage >= 18.0:
        adjusted_need = min(100, round(need_score * 1.15))

    contact_score = 100 if named_senco_found else 30
    mat_score = 100 if is_part_of_mat else 50
    ofsted_score = 100 if has_ofsted_quote else 40

    overall = round(
        (adjusted_need * 0.35)
        + (fit_score * 0.25)
        + (contact_score * 0.20)
        + (mat_score * 0.10)
        + (ofsted_score * 0.10)
    )

    overall = max(0, min(100, overall))

    if overall >= 75:
        priority = "Immediate Focus"
    elif overall >= 55:
        priority = "Target School"
    elif overall >= 35:
        priority = "Monitor"
    else:
        priority = "Low Priority"

    return SchoolScoreResult(overall_score=overall, priority=priority)
