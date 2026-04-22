"""Unit tests for Risk Alert detectors — all 15+ risk rules."""
from __future__ import annotations

import pytest
from datetime import date

from src.agents.risk_alert.detectors import (
    detect_placement_mismatches,
    detect_rate_violations,
    detect_markup_violations,
    detect_amount_anomalies,
    detect_hours_mismatches,
    detect_duplicate_charges,
)


# ── Placement Date Mismatches ──────────────────────────────────────


class TestPlacementMismatches:
    def test_active_placement_past_end_date(self):
        p = [{"bullhorn_id": "1", "status": "Approved", "end_date": "2024-01-01", "candidate_name": "John"}]
        risks = detect_placement_mismatches(
            p, approved_statuses=["approved"], inactive_statuses=["terminated"],
            today=date(2025, 6, 1),
        )
        assert len(risks) == 1
        assert risks[0].risk_type == "active_placement_date_mismatch"

    def test_inactive_placement_future_end_date(self):
        p = [{"bullhorn_id": "2", "status": "Terminated", "end_date": "2026-12-31", "candidate_name": "Jane"}]
        risks = detect_placement_mismatches(
            p, approved_statuses=["approved"], inactive_statuses=["terminated"],
            today=date(2025, 6, 1),
        )
        assert len(risks) == 1
        assert risks[0].risk_type == "inactive_placement_date_mismatch"

    def test_no_mismatch_active_future_end(self):
        p = [{"bullhorn_id": "3", "status": "Approved", "end_date": "2026-12-31", "candidate_name": "OK"}]
        risks = detect_placement_mismatches(
            p, approved_statuses=["approved"], inactive_statuses=["terminated"],
            today=date(2025, 6, 1),
        )
        assert len(risks) == 0

    def test_no_end_date_no_risk(self):
        p = [{"bullhorn_id": "4", "status": "Approved", "candidate_name": "NoEnd"}]
        risks = detect_placement_mismatches(
            p, approved_statuses=["approved"], inactive_statuses=["terminated"],
        )
        assert len(risks) == 0


# ── Rate Violations ────────────────────────────────────────────────


class TestRateViolations:
    def test_below_federal_min_wage(self):
        p = [{"bullhorn_id": "1", "pay_rate": 5.00, "bill_rate": 10.0, "candidate_name": "Low"}]
        risks = detect_rate_violations(p, federal_min_wage=7.25)
        types = {r.risk_type for r in risks}
        assert "below_federal_min_wage" in types

    def test_below_state_min_wage(self):
        p = [{"bullhorn_id": "1", "pay_rate": 10.00, "bill_rate": 20.0, "state": "CA", "candidate_name": "CA"}]
        risks = detect_rate_violations(p, federal_min_wage=7.25)
        types = {r.risk_type for r in risks}
        assert "below_state_min_wage" in types  # CA min is $16.50

    def test_state_wage_override(self):
        p = [{"bullhorn_id": "1", "pay_rate": 10.00, "bill_rate": 20.0, "state": "TX", "candidate_name": "TX"}]
        # TX normally $7.25, but override to $12
        risks = detect_rate_violations(p, state_wage_overrides={"TX": 12.00})
        types = {r.risk_type for r in risks}
        assert "below_state_min_wage" in types

    def test_high_pay_rate(self):
        p = [{"bullhorn_id": "1", "pay_rate": 200.0, "bill_rate": 300.0, "candidate_name": "High"}]
        risks = detect_rate_violations(p, high_pay_rate=150.0)
        types = {r.risk_type for r in risks}
        assert "high_pay_rate" in types

    def test_high_bill_rate(self):
        p = [{"bullhorn_id": "1", "pay_rate": 50.0, "bill_rate": 300.0, "candidate_name": "HighBill"}]
        risks = detect_rate_violations(p, high_bill_rate=225.0)
        types = {r.risk_type for r in risks}
        assert "high_bill_rate" in types

    def test_normal_rates_no_risk(self):
        p = [{"bullhorn_id": "1", "pay_rate": 25.0, "bill_rate": 40.0, "candidate_name": "OK"}]
        risks = detect_rate_violations(p)
        assert len(risks) == 0


# ── Markup Violations ──────────────────────────────────────────────


class TestMarkupViolations:
    def test_negative_markup(self):
        p = [{"bullhorn_id": "1", "pay_rate": 50.0, "bill_rate": 40.0, "candidate_name": "Neg"}]
        risks = detect_markup_violations(p)
        assert len(risks) == 1
        assert risks[0].risk_type == "negative_markup"
        assert risks[0].financial_impact == 10.0

    def test_low_markup(self):
        p = [{"bullhorn_id": "1", "pay_rate": 50.0, "bill_rate": 52.0, "candidate_name": "Low"}]
        risks = detect_markup_violations(p, low_markup_pct=10.0)
        assert len(risks) == 1
        assert risks[0].risk_type == "low_markup"

    def test_high_markup(self):
        p = [{"bullhorn_id": "1", "pay_rate": 10.0, "bill_rate": 100.0, "candidate_name": "High"}]
        risks = detect_markup_violations(p, high_markup_pct=250.0)
        assert len(risks) == 1
        assert risks[0].risk_type == "high_markup"

    def test_normal_markup(self):
        p = [{"bullhorn_id": "1", "pay_rate": 30.0, "bill_rate": 50.0, "candidate_name": "OK"}]
        risks = detect_markup_violations(p, low_markup_pct=10.0, high_markup_pct=250.0)
        assert len(risks) == 0


# ── Amount Anomalies ───────────────────────────────────────────────


class TestAmountAnomalies:
    def test_negative_pay(self):
        c = [{"pay_amount": -100.0, "bill_amount": 50.0, "candidate_name": "Neg"}]
        risks = detect_amount_anomalies(c)
        types = {r.risk_type for r in risks}
        assert "negative_pay_amount" in types

    def test_negative_bill(self):
        c = [{"pay_amount": 50.0, "bill_amount": -100.0, "candidate_name": "Neg"}]
        risks = detect_amount_anomalies(c)
        types = {r.risk_type for r in risks}
        assert "negative_bill_amount" in types

    def test_high_pay_amount(self):
        c = [{"pay_amount": 10000.0, "bill_amount": 12000.0, "candidate_name": "High"}]
        risks = detect_amount_anomalies(c, high_pay_amount=5000.0)
        types = {r.risk_type for r in risks}
        assert "high_pay_amount" in types

    def test_high_bill_amount(self):
        c = [{"pay_amount": 3000.0, "bill_amount": 10000.0, "candidate_name": "High"}]
        risks = detect_amount_anomalies(c, high_bill_amount=7500.0)
        types = {r.risk_type for r in risks}
        assert "high_bill_amount" in types

    def test_pay_no_bill(self):
        c = [{"pay_amount": 500.0, "bill_amount": 0.0, "candidate_name": "PayOnly"}]
        risks = detect_amount_anomalies(c)
        types = {r.risk_type for r in risks}
        assert "pay_no_bill" in types

    def test_bill_no_pay(self):
        c = [{"pay_amount": 0.0, "bill_amount": 500.0, "candidate_name": "BillOnly"}]
        risks = detect_amount_anomalies(c)
        types = {r.risk_type for r in risks}
        assert "bill_no_pay" in types


# ── Hours Mismatches ───────────────────────────────────────────────


class TestHoursMismatches:
    def test_pay_bill_hours_differ(self):
        c = [{"pay_hours": 40.0, "bill_hours": 35.0, "candidate_name": "Diff"}]
        risks = detect_hours_mismatches(c)
        assert len(risks) == 1
        assert risks[0].risk_type == "pay_bill_hours_mismatch"

    def test_rate_card_mismatch(self):
        c = [{
            "transaction_pay_rate": 50.0, "placement_pay_rate": 30.0,
            "pay_hours": 40.0, "bill_hours": 40.0,
            "candidate_name": "RateMismatch",
        }]
        risks = detect_hours_mismatches(c, bill_rate_mismatch_pct=20.0)
        types = {r.risk_type for r in risks}
        assert "pay_rate_card_mismatch" in types

    def test_matching_hours_no_risk(self):
        c = [{"pay_hours": 40.0, "bill_hours": 40.0, "candidate_name": "OK"}]
        risks = detect_hours_mismatches(c)
        assert len(risks) == 0


# ── Duplicate Charges ──────────────────────────────────────────────


class TestDuplicateCharges:
    def test_duplicate_detected(self):
        c = [
            {"placement_id": "P1", "period_end": "2025-03-14", "pay_amount": 1000.0, "bill_amount": 1500.0, "candidate_name": "Dup"},
            {"placement_id": "P1", "period_end": "2025-03-14", "pay_amount": 1000.0, "bill_amount": 1500.0, "candidate_name": "Dup"},
        ]
        risks = detect_duplicate_charges(c)
        assert len(risks) == 1
        assert risks[0].risk_type == "duplicate_charge"
        assert risks[0].details["duplicate_count"] == 2

    def test_no_duplicates(self):
        c = [
            {"placement_id": "P1", "period_end": "2025-03-14", "pay_amount": 1000.0, "bill_amount": 1500.0},
            {"placement_id": "P2", "period_end": "2025-03-14", "pay_amount": 1000.0, "bill_amount": 1500.0},
        ]
        risks = detect_duplicate_charges(c)
        assert len(risks) == 0
