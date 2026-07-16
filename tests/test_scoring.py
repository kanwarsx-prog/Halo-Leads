import pytest

from app.scoring import apply_pursuit_gate, calculate_lead_score


def test_high_priority_score() -> None:
    """All-high inputs should produce immediate_pursuit."""
    result = calculate_lead_score(
        servicenow_confidence=95,
        basic_use_likelihood=90,
        cost_pressure=80,
        renewal_proximity=85,
        migration_fit=85,
    )

    assert result.overall_score >= 80
    assert result.priority == "immediate_pursuit"


def test_low_score_produces_do_not_pursue() -> None:
    result = calculate_lead_score(
        servicenow_confidence=10,
        basic_use_likelihood=10,
        cost_pressure=10,
        renewal_proximity=10,
        migration_fit=10,
    )

    assert result.overall_score < 45
    assert result.priority == "do_not_pursue"


def test_score_in_monitor_band() -> None:
    result = calculate_lead_score(
        servicenow_confidence=50,
        basic_use_likelihood=50,
        cost_pressure=50,
        renewal_proximity=50,
        migration_fit=50,
    )

    assert 45 <= result.overall_score < 65
    assert result.priority == "monitor"


def test_score_in_research_and_nurture_band() -> None:
    result = calculate_lead_score(
        servicenow_confidence=70,
        basic_use_likelihood=70,
        cost_pressure=70,
        renewal_proximity=70,
        migration_fit=70,
    )

    assert 65 <= result.overall_score < 80
    assert result.priority == "research_and_nurture"


def test_unverified_account_is_gated() -> None:
    """Unverified ServiceNow status must hard-cap score to <= 44."""
    score, priority = apply_pursuit_gate(
        overall_score=87,
        priority="immediate_pursuit",
        servicenow_status="unverified",
    )

    assert score == 44
    assert priority == "do_not_pursue"


def test_possible_status_prevents_immediate_pursuit() -> None:
    score, priority = apply_pursuit_gate(
        overall_score=85,
        priority="immediate_pursuit",
        servicenow_status="possible",
    )

    assert score <= 79
    assert priority == "research_and_nurture"


def test_confirmed_status_does_not_alter_score() -> None:
    score, priority = apply_pursuit_gate(
        overall_score=82,
        priority="immediate_pursuit",
        servicenow_status="confirmed",
    )

    assert score == 82
    assert priority == "immediate_pursuit"


def test_rejects_invalid_component() -> None:
    """Component scores outside [0, 100] must raise ValueError."""
    with pytest.raises(ValueError):
        calculate_lead_score(
            servicenow_confidence=101,
            basic_use_likelihood=50,
            cost_pressure=50,
            renewal_proximity=50,
            migration_fit=50,
        )


def test_rejects_negative_component() -> None:
    with pytest.raises(ValueError):
        calculate_lead_score(
            servicenow_confidence=50,
            basic_use_likelihood=-1,
            cost_pressure=50,
            renewal_proximity=50,
            migration_fit=50,
        )


def test_boundary_values_accepted() -> None:
    """0 and 100 are both valid boundary values."""
    result = calculate_lead_score(
        servicenow_confidence=0,
        basic_use_likelihood=100,
        cost_pressure=0,
        renewal_proximity=100,
        migration_fit=0,
    )
    # weighted: 0*0.15 + 100*0.25 + 0*0.20 + 100*0.20 + 0*0.20 = 45
    assert result.overall_score == 45
