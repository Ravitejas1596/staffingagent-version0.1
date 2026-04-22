"""Unit tests for Collections and Compliance and Invoice Matching detectors."""
from __future__ import annotations

import pytest
from datetime import date

from src.agents.collections.detectors import prioritize_ar, group_by_client
from src.agents.compliance.detectors import (
    check_credential_expiry,
    check_overtime_classification,
    check_contract_terms,
    check_worker_classification,
)
from src.agents.invoice_matching.detectors import (
    match_invoices_to_charges,
    detect_duplicate_invoices,
)


# ── Collections: AR Prioritization ─────────────────────────────────


class TestARPrioritization:
    def test_basic_scoring(self):
        ar = [
            {"invoice_id": "INV-1", "client_name": "Client A", "amount": 5000, "days_outstanding": 45},
            {"invoice_id": "INV-2", "client_name": "Client B", "amount": 50000, "days_outstanding": 90},
        ]
        results = prioritize_ar(ar)
        assert len(results) == 2
        # Higher amount + more days should rank first
        assert results[0].invoice_id == "INV-2"
        assert results[0].priority_tier in ("critical", "high")

    def test_escalation_stages(self):
        ar = [
            {"invoice_id": "1", "client_name": "A", "amount": 1000, "days_outstanding": 10},
            {"invoice_id": "2", "client_name": "B", "amount": 1000, "days_outstanding": 35},
            {"invoice_id": "3", "client_name": "C", "amount": 1000, "days_outstanding": 65},
            {"invoice_id": "4", "client_name": "D", "amount": 1000, "days_outstanding": 95},
        ]
        results = prioritize_ar(ar)
        stages = {r.invoice_id: r.escalation_stage for r in results}
        assert stages["1"] == "reminder"
        assert stages["2"] == "follow_up"
        assert stages["3"] == "escalation"
        assert stages["4"] == "legal"

    def test_critical_amount_tier(self):
        ar = [{"invoice_id": "1", "client_name": "Big", "amount": 75000, "days_outstanding": 15}]
        results = prioritize_ar(ar, critical_priority_amount=50000)
        assert results[0].priority_tier == "critical"

    def test_zero_amount_skipped(self):
        ar = [{"invoice_id": "1", "client_name": "Zero", "amount": 0, "days_outstanding": 90}]
        assert len(prioritize_ar(ar)) == 0

    def test_group_by_client(self):
        ar = [
            {"invoice_id": "1", "client_name": "X", "amount": 1000, "days_outstanding": 30},
            {"invoice_id": "2", "client_name": "X", "amount": 2000, "days_outstanding": 60},
            {"invoice_id": "3", "client_name": "Y", "amount": 3000, "days_outstanding": 45},
        ]
        results = prioritize_ar(ar)
        groups = group_by_client(results)
        assert len(groups["X"]) == 2
        assert len(groups["Y"]) == 1


# ── Compliance: Credential Expiry ──────────────────────────────────


class TestCredentialExpiry:
    def test_expired_credential(self):
        creds = [{"id": "1", "candidate_name": "John", "credential_type": "RN License", "expiry_date": "2025-01-01"}]
        vs = check_credential_expiry(creds, today=date(2025, 3, 1))
        assert len(vs) == 1
        assert vs[0].violation_type == "credential_expired"
        assert vs[0].severity == "critical"

    def test_critical_expiry(self):
        creds = [{"id": "2", "candidate_name": "Jane", "credential_type": "CPR", "expiry_date": "2025-03-05"}]
        vs = check_credential_expiry(creds, critical_days=7, today=date(2025, 3, 1))
        assert len(vs) == 1
        assert vs[0].violation_type == "credential_expiring_critical"

    def test_warning_expiry(self):
        creds = [{"id": "3", "candidate_name": "Bob", "credential_type": "BLS", "expiry_date": "2025-03-20"}]
        vs = check_credential_expiry(creds, warning_days=30, today=date(2025, 3, 1))
        assert len(vs) == 1
        assert vs[0].violation_type == "credential_expiring_warning"

    def test_valid_credential(self):
        creds = [{"id": "4", "candidate_name": "OK", "credential_type": "RN", "expiry_date": "2026-12-31"}]
        vs = check_credential_expiry(creds, today=date(2025, 3, 1))
        assert len(vs) == 0


class TestOvertimeClassification:
    def test_exempt_with_ot(self):
        p = [{"bullhorn_id": "1", "candidate_name": "Ex", "employee_type": "Exempt", "ot_hours": 10}]
        vs = check_overtime_classification(p)
        assert len(vs) == 1
        assert vs[0].violation_type == "exempt_with_overtime"

    def test_missing_overtime(self):
        p = [{"bullhorn_id": "2", "candidate_name": "No", "employee_type": "Hourly", "total_hours": 50, "ot_hours": 0}]
        vs = check_overtime_classification(p)
        assert len(vs) == 1
        assert vs[0].violation_type == "missing_overtime"


class TestContractTerms:
    def test_duration_exceeded(self):
        p = [{"bullhorn_id": "1", "candidate_name": "Long", "start_date": "2023-01-01", "contract_max_months": 12}]
        vs = check_contract_terms(p, today=date(2025, 6, 1))
        assert len(vs) == 1
        assert vs[0].violation_type == "contract_duration_exceeded"

    def test_hours_exceeded(self):
        p = [{"bullhorn_id": "2", "candidate_name": "Overwork", "contract_max_hours": 1000, "cumulative_hours": 1200}]
        vs = check_contract_terms(p)
        assert len(vs) == 1
        assert vs[0].violation_type == "contract_hours_exceeded"


class TestWorkerClassification:
    def test_long_tenure_1099(self):
        p = [{"bullhorn_id": "1", "candidate_name": "Contractor", "employee_type": "1099", "duration_months": 18}]
        vs = check_worker_classification(p)
        assert len(vs) == 1
        assert vs[0].violation_type == "worker_misclassification_risk"


# ── Invoice Matching ───────────────────────────────────────────────


class TestInvoiceMatching:
    def test_exact_match(self):
        invoices = [{"invoice_id": "I1", "client_name": "Acme", "amount": 5000}]
        charges = [{"charge_id": "C1", "client_name": "Acme", "amount": 5000}]
        matches, exceptions = match_invoices_to_charges(invoices, charges)
        assert len(matches) == 1
        assert matches[0].match_method == "exact"
        assert matches[0].confidence >= 0.99

    def test_amount_tolerance_match(self):
        invoices = [{"invoice_id": "I1", "client_name": "Acme", "amount": 5000}]
        charges = [{"charge_id": "C1", "client_name": "Acme", "amount": 4950}]
        matches, exceptions = match_invoices_to_charges(invoices, charges, amount_tolerance_pct=2.0)
        assert len(matches) == 1
        assert matches[0].match_method == "amount_match"

    def test_unmatched_invoice(self):
        invoices = [{"invoice_id": "I1", "client_name": "Acme", "amount": 5000}]
        charges = [{"charge_id": "C1", "client_name": "OtherCo", "amount": 5000}]
        matches, exceptions = match_invoices_to_charges(invoices, charges)
        assert len(matches) == 0
        types = {e.exception_type for e in exceptions}
        assert "unmatched_invoice" in types

    def test_uninvoiced_charge(self):
        invoices = []
        charges = [{"charge_id": "C1", "client_name": "Acme", "amount": 5000}]
        matches, exceptions = match_invoices_to_charges(invoices, charges)
        types = {e.exception_type for e in exceptions}
        assert "uninvoiced_charge" in types

    def test_duplicate_invoices(self):
        invoices = [
            {"invoice_id": "I1", "client_name": "Acme", "amount": 5000},
            {"invoice_id": "I2", "client_name": "Acme", "amount": 5000},
        ]
        dups = detect_duplicate_invoices(invoices)
        assert len(dups) == 1
        assert dups[0].exception_type == "duplicate_invoice"
