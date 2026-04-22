"""Unit tests for the state minimum wage lookup module."""
from __future__ import annotations

import pytest

from src.agents.risk_alert.state_wages import (
    FEDERAL_MIN_WAGE,
    STATE_MIN_WAGES,
    get_min_wage,
)


class TestGetMinWage:
    def test_known_state(self):
        assert get_min_wage("CA") == 16.50
        assert get_min_wage("WA") == 16.66
        assert get_min_wage("NY") == 15.50

    def test_case_insensitive(self):
        assert get_min_wage("ca") == get_min_wage("CA")
        assert get_min_wage("Ca") == get_min_wage("CA")

    def test_federal_fallback(self):
        assert get_min_wage("TX") == 7.25
        assert get_min_wage("XX") == FEDERAL_MIN_WAGE

    def test_none_returns_federal(self):
        assert get_min_wage(None) == FEDERAL_MIN_WAGE

    def test_empty_returns_federal(self):
        assert get_min_wage("") == FEDERAL_MIN_WAGE

    def test_override_wins(self):
        assert get_min_wage("TX", overrides={"TX": 15.00}) == 15.00

    def test_override_does_not_affect_other_states(self):
        assert get_min_wage("CA", overrides={"TX": 15.00}) == 16.50

    def test_all_50_states_present(self):
        assert len(STATE_MIN_WAGES) >= 51  # 50 states + DC

    def test_no_state_below_federal(self):
        for state, wage in STATE_MIN_WAGES.items():
            assert wage >= FEDERAL_MIN_WAGE, f"{state} wage {wage} below federal"
