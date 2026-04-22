"""LangGraph nodes for the Time Anomaly Agent v1 state machine.

State machine (plan §Architecture):

    detect -> outreach -> wait_recheck -> escalate_hitl -> close
                              |                              ^
                              └─── employee corrected ────────┘

Each node is a coroutine matching LangGraph's signature
``async def node(state: TimeAnomalyAlertState) -> dict[str, Any]``. It
returns a partial-state dict; LangGraph merges that into the running
state object and routes via the conditional edges defined in
``graph.py``.

Side effects (Bullhorn writes, Twilio sends, DB writes) flow through
``src/api/gateway.py``, ``src/integrations/twilio_sms.py``, and
``src/agents/time_anomaly/alerts.py``. Nodes never call external APIs
directly, per the project constitution.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from app_platform.api.database import get_tenant_session
from app_platform.api.message_templates import render
from src.agents.time_anomaly import alerts as alert_repo
from src.agents.time_anomaly.config import load_config
from src.agents.time_anomaly.detectors import (
    AlertCandidate,
    DetectContext,
    detect_group_a1,
    detect_group_a2,
    detect_group_b,
    detect_group_c,
)
from src.agents.time_anomaly.benchmarks import HistoricalAverageProvider
from src.agents.time_anomaly.config import SLABand, TimeAnomalyConfig
from src.agents.time_anomaly.state import TimeAnomalyAlertState
from src.agents.time_anomaly.timers import schedule_timer
from src.api import gateway
from src.integrations.twilio_sms import (
    TwilioConfigError,
    TwilioSendError,
    get_twilio_client,
)

logger = logging.getLogger(__name__)

# Routing labels — centralized so graph.py's conditional edges and the
# returned ``next`` key can never drift out of sync.
ROUTE_OUTREACH = "outreach"
ROUTE_WAIT = "wait_recheck"
ROUTE_ESCALATE = "escalate_hitl"
ROUTE_CLOSE = "close"
ROUTE_END = "__end__"


def _to_uuid(val: str | None) -> UUID | None:
    if val is None:
        return None
    return UUID(val) if not isinstance(val, UUID) else val


async def detect_node(state: TimeAnomalyAlertState) -> dict[str, Any]:
    """Run the rule-based detectors, suppression checks, and alert creation.

    Returns:
        - ``{"next": ROUTE_END}`` when no alert fires (quiet path).
        - ``{"next": ROUTE_OUTREACH, "alert_id": ..., "alert_candidate": ...}``
          when an alert is created and we should proceed to outreach.
    """
    tenant_id = state["tenant_id"]
    placement_id = _to_uuid(state["placement_id"])
    candidate_id = _to_uuid(state.get("candidate_id"))
    pay_period_start: date = state["pay_period_start"]
    pay_period_end: date = state["pay_period_end"]
    bullhorn_placement_id = state["bullhorn_placement_id"]
    assert placement_id is not None  # required input

    async with get_tenant_session(tenant_id) as session:
        cfg = await load_config(
            session, tenant_id=UUID(tenant_id), dry_run=state.get("dry_run", False)
        )

        # Timesheet lookup (Bullhorn read). Failures here are retried by the
        # graph's retry policy rather than firing false alerts.
        try:
            timesheet = await gateway.get_timesheet_by_placement_and_period(
                tenant_id=tenant_id,
                placement_id=bullhorn_placement_id,
                pay_period_start=pay_period_start,
                pay_period_end=pay_period_end,
            )
        except Exception as exc:  # pragma: no cover — transport failures
            logger.exception("time_anomaly.detect.bullhorn_read_failed")
            return {"next": ROUTE_END, "error": f"bullhorn_read_failed: {exc}"}

        ctx = DetectContext(
            tenant_id=UUID(tenant_id),
            placement_id=placement_id,
            candidate_id=candidate_id,
            pay_period_start=pay_period_start,
            pay_period_end=pay_period_end,
            bullhorn_placement_id=bullhorn_placement_id,
            current_timesheet=timesheet,
        )

        # Priority routing:
        #   - No timesheet: try A1 (first miss) then A2 (consecutive miss).
        #     A1 defers to A2 automatically when a prior cycle already
        #     missed, so we just run both in sequence and take the first
        #     non-None result.
        #   - Timesheet exists: try B (static hours-over-limit) then C
        #     (variance from the employee's typical pattern). B fires
        #     the most severe variant per timesheet, C suppresses itself
        #     when the exception_registry has a matching dismissal.
        candidate: AlertCandidate | None = None
        if ctx.current_timesheet is None:
            candidate = await detect_group_a1(session, ctx=ctx, cfg=cfg)
            if candidate is None:
                candidate = await detect_group_a2(session, ctx=ctx, cfg=cfg)
        else:
            candidate = await detect_group_b(session, ctx=ctx, cfg=cfg)
            if candidate is None:
                benchmark_provider = HistoricalAverageProvider(
                    lookback_weeks=cfg.group_c.lookback_weeks,
                    basis=cfg.group_c.basis,
                )
                candidate = await detect_group_c(
                    session,
                    ctx=ctx,
                    cfg=cfg,
                    benchmark_provider=benchmark_provider,
                )

        if candidate is None:
            return {
                "next": ROUTE_END,
                "current_timesheet": timesheet,
                "alert_candidate": None,
            }

        created = await alert_repo.create_alert(
            session,
            tenant_id=UUID(tenant_id),
            agent_type="time_anomaly",
            alert_type=candidate.alert_type,
            severity=candidate.severity,
            placement_id=placement_id,
            candidate_id=candidate_id,
            pay_period_start=pay_period_start,
            pay_period_end=pay_period_end,
            trigger_context=candidate.trigger_context,
        )

    return {
        "next": ROUTE_OUTREACH,
        "current_timesheet": timesheet,
        "alert_candidate": {
            "alert_type": candidate.alert_type,
            "severity": candidate.severity,
            "trigger_context": candidate.trigger_context,
        },
        "alert_id": str(created.alert_id),
    }


async def outreach_node(state: TimeAnomalyAlertState) -> dict[str, Any]:
    """Render the SMS template, generate a BTE link, and send via Twilio.

    Honors ``state['dry_run']`` — in dry-run the Twilio send returns a
    synthetic result and no Bullhorn state changes occur, but all DB
    events are still written so the end-to-end trace is visible in
    ``agent_alerts`` and ``agent_alert_events``.
    """
    tenant_id = state["tenant_id"]
    alert_id_str = state["alert_id"]
    if alert_id_str is None:
        return {"next": ROUTE_END, "error": "outreach_node called without alert_id"}
    alert_id = UUID(alert_id_str)
    candidate = state.get("alert_candidate") or {}
    alert_type = candidate.get("alert_type", "")

    async with get_tenant_session(tenant_id) as session:
        # Template key is derived from the alert type: all Group A1 alerts
        # use 'time_anomaly.group_a1.sms', etc. Keeps template routing
        # out of the node body.
        template_key = f"time_anomaly.{_alert_group(alert_type)}.sms"
        variables = _build_template_variables(state)

        try:
            rendered = await render(
                session,
                template_key=template_key,
                tenant_id=UUID(tenant_id),
                variables=variables,
            )
        except Exception as exc:
            await alert_repo.append_event(
                session,
                alert_id=alert_id,
                tenant_id=UUID(tenant_id),
                event_type="sms_skipped_no_consent",  # closest event_type in v1
                actor_type="agent",
                actor_id="time_anomaly",
                metadata={"error": f"template_render_failed: {exc}"},
            )
            return {"next": ROUTE_ESCALATE, "error": f"template_render_failed: {exc}"}

        # Generate BTE link. While blocked on Josh's Apr 22 confirmation,
        # this raises NotImplementedError — we catch it, log, and skip the
        # SMS (but still escalate so a human closes the loop manually).
        bte_link_url: str | None = None
        try:
            bte = await gateway.generate_bte_timesheet_link(
                tenant_id=tenant_id,
                candidate_id=state.get("bullhorn_candidate_id") or "",
                placement_id=state["bullhorn_placement_id"],
                pay_period_end=state["pay_period_end"],
            )
            bte_link_url = bte.url
        except NotImplementedError:
            logger.warning("time_anomaly.outreach.bte_not_implemented")

        # Send SMS.
        twilio = get_twilio_client(dry_run=state.get("dry_run", False))
        messaging_service_sid = await _load_tenant_messaging_sid(session, UUID(tenant_id))
        if not messaging_service_sid:
            await alert_repo.append_event(
                session,
                alert_id=alert_id,
                tenant_id=UUID(tenant_id),
                event_type="sms_skipped_no_consent",
                actor_type="agent",
                actor_id="time_anomaly",
                metadata={"reason": "tenant_missing_messaging_service_sid"},
            )
            await alert_repo.transition_state(
                session, alert_id=alert_id, new_state="escalated_hitl"
            )
            return {
                "next": ROUTE_ESCALATE,
                "sms_skipped_reason": "tenant_missing_messaging_service_sid",
            }

        to_number = variables.get("_employee_phone", "")  # not a rendered var
        sms_sid: str | None = None
        sms_skipped_reason: str | None = None
        try:
            result = await twilio.send(
                to=to_number or "+10000000000",
                body=rendered.body,
                messaging_service_sid=messaging_service_sid,
            )
            sms_sid = result.sid
        except (TwilioConfigError, TwilioSendError) as exc:
            sms_skipped_reason = f"twilio_error: {exc}"
            logger.exception("time_anomaly.outreach.twilio_failed")

        # Record the event + state transition.
        event_type = "sms_sent" if sms_sid else "sms_skipped_no_consent"
        await alert_repo.append_event(
            session,
            alert_id=alert_id,
            tenant_id=UUID(tenant_id),
            event_type=event_type,
            actor_type="agent",
            actor_id="time_anomaly",
            metadata={
                "sms_sid": sms_sid,
                "messaging_service_sid": messaging_service_sid,
                "template_key": template_key,
                "template_source": rendered.source,
                "bte_link_url": bte_link_url,
                "dry_run": state.get("dry_run", False),
                "skipped_reason": sms_skipped_reason,
            },
        )
        await alert_repo.transition_state(
            session, alert_id=alert_id, new_state="outreach_sent"
        )

        severity = candidate.get("severity", "medium")
        band = _sla_band_for(
            await _resolved_config(session, UUID(tenant_id), state.get("dry_run", False)),
            severity,
        )
        timer_id = await schedule_timer(
            alert_id=alert_id,
            tenant_id=UUID(tenant_id),
            thread_id=state.get("agent_run_id"),
            reason="first_reminder",
            delay_seconds=band.first_reminder_hours * 3600,
        )

    # Routing: when the SLA timer queue is configured (production), the
    # timer message is what wakes wait_recheck — the graph should park
    # here. When it's unset (tests / local dev), fall through so the
    # end-to-end flow is exercisable synchronously.
    next_route = ROUTE_END if timer_id else ROUTE_WAIT
    return {
        "next": next_route,
        "sms_sid": sms_sid,
        "sms_skipped_reason": sms_skipped_reason,
        "bte_link_url": bte_link_url,
        "rendered_body": rendered.body,
        "sla_timer_id": timer_id,
    }


async def wait_recheck_node(state: TimeAnomalyAlertState) -> dict[str, Any]:
    """Poll Bullhorn for an updated timesheet.

    In the durable Postgres-checkpointed deployment, this node parks the
    LangGraph thread until the SQS timer worker resumes it. In the
    in-process/memory deployment (tests, dev), callers drive the loop
    explicitly. Either way the node's logic is: re-query Bullhorn; if
    the timesheet is now present, close; otherwise escalate.
    """
    tenant_id = state["tenant_id"]
    alert_id = UUID(state["alert_id"] or "")

    async with get_tenant_session(tenant_id) as session:
        try:
            timesheet = await gateway.get_timesheet_by_placement_and_period(
                tenant_id=tenant_id,
                placement_id=state["bullhorn_placement_id"],
                pay_period_start=state["pay_period_start"],
                pay_period_end=state["pay_period_end"],
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("time_anomaly.wait_recheck.bullhorn_failed")
            return {"next": ROUTE_ESCALATE, "error": f"bullhorn_read_failed: {exc}"}

        if timesheet is not None:
            await alert_repo.append_event(
                session,
                alert_id=alert_id,
                tenant_id=UUID(tenant_id),
                event_type="closed",
                actor_type="agent",
                actor_id="time_anomaly",
                metadata={"reason": "employee_corrected", "timesheet_id": timesheet.get("id")},
            )
            await alert_repo.transition_state(
                session,
                alert_id=alert_id,
                new_state="resolved",
                resolution="employee_corrected",
            )
            return {
                "next": ROUTE_CLOSE,
                "recheck_timesheet": timesheet,
                "final_state": "resolved",
                "resolution": "employee_corrected",
            }

    return {"next": ROUTE_ESCALATE, "recheck_timesheet": None}


async def escalate_hitl_node(state: TimeAnomalyAlertState) -> dict[str, Any]:
    """Transition the alert to escalated_hitl so the HITL queue picks it up.

    Creation of ``agent_plan_actions`` rows for the HITL resolution options
    lands in PR-E alongside the AlertQueue UI. For now the node emits the
    ``hitl_assigned`` event; the queue endpoint will read off alert state.
    """
    tenant_id = state["tenant_id"]
    alert_id = UUID(state["alert_id"] or "")

    async with get_tenant_session(tenant_id) as session:
        await alert_repo.append_event(
            session,
            alert_id=alert_id,
            tenant_id=UUID(tenant_id),
            event_type="hitl_assigned",
            actor_type="agent",
            actor_id="time_anomaly",
            metadata={"reason": "sla_breach_or_detect_error"},
        )
        await alert_repo.transition_state(
            session, alert_id=alert_id, new_state="escalated_hitl"
        )
    return {
        "next": ROUTE_END,
        "final_state": "escalated_hitl",
    }


async def close_node(state: TimeAnomalyAlertState) -> dict[str, Any]:
    """Terminal node for the resolved path. Event + state transition
    already happened in wait_recheck; this node is a no-op placeholder
    for future post-close hooks (release hold, notify recruiter, etc.)."""
    del state
    return {"next": ROUTE_END}


# ── helpers ─────────────────────────────────────────────────────────


def _alert_group(alert_type: str) -> str:
    """Map alert_type to the template-key group segment.

    'group_a1_first_miss'        -> 'group_a1'
    'group_a2_consecutive_miss'  -> 'group_a2'
    'group_b_reg_over_limit'     -> 'group_b'
    'group_c_variance'           -> 'group_c'
    """
    if alert_type.startswith("group_a1"):
        return "group_a1"
    if alert_type.startswith("group_a2"):
        return "group_a2"
    if alert_type.startswith("group_b"):
        return "group_b"
    if alert_type.startswith("group_c"):
        return "group_c"
    return alert_type  # fallback: pass through


def _build_template_variables(state: TimeAnomalyAlertState) -> dict[str, Any]:
    """Produce the variable map for template rendering.

    Private keys prefixed with ``_`` (e.g. ``_employee_phone``) are
    consumed by the outreach node itself and stripped before handing the
    dict to the template renderer.
    """
    trigger = (state.get("alert_candidate") or {}).get("trigger_context") or {}
    return {
        "employee_first_name": trigger.get("employee_first_name", "there"),
        "week_ending_date": state["pay_period_end"].isoformat(),
        "bte_link": trigger.get("bte_link", "[pending]"),
        "recruiter_name": trigger.get("recruiter_name", "your recruiter"),
        "company_short_name": trigger.get("company_short_name", "StaffingAgent"),
        "pay_period_start": state["pay_period_start"].isoformat(),
        "pay_period_end": state["pay_period_end"].isoformat(),
        "_employee_phone": trigger.get("employee_phone", ""),
    }


async def _load_tenant_messaging_sid(session: Any, tenant_id: UUID) -> str | None:
    """Read the per-tenant Twilio Messaging Service SID from ``tenants``."""
    from sqlalchemy import select

    from app_platform.api.models import Tenant

    row = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    return row.twilio_messaging_service_sid if row else None


async def _resolved_config(
    session: Any, tenant_id: UUID, dry_run: bool
) -> TimeAnomalyConfig:
    """Re-load (or re-use) the merged tenant config. Outreach only needs
    SLA bands, so this is cheap."""
    from src.agents.time_anomaly.config import load_config

    return await load_config(session, tenant_id=tenant_id, dry_run=dry_run)


def _sla_band_for(cfg: TimeAnomalyConfig, severity: str) -> SLABand:
    """Look up the SLA band for a severity, falling back to ``medium``
    if the requested severity isn't configured (shouldn't happen, but
    defensive code here protects against a mis-seeded config)."""
    if severity in cfg.sla_bands:
        return cfg.sla_bands[severity]
    return cfg.sla_bands.get("medium", SLABand(first_reminder_hours=4, escalation_hours=24))


# ── SQS timer resume path ────────────────────────────────────────────


async def resume_alert(
    *,
    alert_id: UUID,
    tenant_id: UUID,
    reason: str,
) -> dict[str, Any]:
    """Public entry point for the SLA timer worker.

    The worker never imports the graph — it imports this function.
    That keeps the graph module's heavier dependencies out of the
    worker startup path and gives us a narrow, well-tested resume API.

    Behavior by reason:

    - ``first_reminder``: re-poll Bullhorn. If the timesheet is now
      present, close the alert. Otherwise enqueue the escalation timer
      and return (alert stays in ``outreach_sent``).
    - ``escalate``: re-poll Bullhorn once more. If the timesheet is
      present, close. Otherwise transition to ``escalated_hitl`` so the
      HITL queue picks it up.
    """
    from sqlalchemy import select

    from app_platform.api import models
    from app_platform.api.database import get_tenant_session as _session

    tenant_id_str = str(tenant_id)
    async with _session(tenant_id_str) as session:
        alert = (
            await session.execute(
                select(models.AgentAlert).where(models.AgentAlert.id == alert_id)
            )
        ).scalar_one_or_none()
        if alert is None:
            logger.warning(
                "time_anomaly.resume_alert.missing_alert",
                extra={"alert_id": str(alert_id)},
            )
            return {"status": "missing"}
        if alert.state == "resolved":
            logger.info(
                "time_anomaly.resume_alert.already_resolved",
                extra={"alert_id": str(alert_id)},
            )
            return {"status": "already_resolved"}

        placement = await session.get(models.Placement, alert.placement_id) if alert.placement_id else None
        bullhorn_placement_id = placement.bullhorn_id if placement else ""

        try:
            timesheet = await gateway.get_timesheet_by_placement_and_period(
                tenant_id=tenant_id_str,
                placement_id=bullhorn_placement_id,
                pay_period_start=alert.pay_period_start,
                pay_period_end=alert.pay_period_end,
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("time_anomaly.resume_alert.bullhorn_failed")
            return {"status": "bullhorn_error", "error": str(exc)}

        if timesheet is not None:
            await alert_repo.append_event(
                session,
                alert_id=alert_id,
                tenant_id=tenant_id,
                event_type="closed",
                actor_type="agent",
                actor_id="time_anomaly",
                metadata={"reason": "employee_corrected", "timesheet_id": timesheet.get("id")},
            )
            await alert_repo.transition_state(
                session,
                alert_id=alert_id,
                new_state="resolved",
                resolution="employee_corrected",
            )
            return {"status": "resolved", "final_state": "resolved"}

        if reason == "first_reminder":
            cfg = await _resolved_config(session, tenant_id, dry_run=False)
            band = _sla_band_for(cfg, alert.severity)
            timer_id = await schedule_timer(
                alert_id=alert_id,
                tenant_id=tenant_id,
                thread_id=alert.langgraph_thread_id,
                reason="escalate",
                delay_seconds=max(
                    band.escalation_hours - band.first_reminder_hours, 1
                ) * 3600,
            )
            await alert_repo.append_event(
                session,
                alert_id=alert_id,
                tenant_id=tenant_id,
                event_type="first_reminder_sent",
                actor_type="agent",
                actor_id="time_anomaly",
                metadata={"escalation_timer_id": timer_id},
            )
            # Optional: send a reminder SMS here. Skipped in v1 to keep
            # the reply behavior predictable; tenants can opt-in via a
            # follow-up PR once we've observed first-reminder response
            # rates in pilot data.
            return {"status": "waiting_for_escalation", "timer_id": timer_id}

        # reason == "escalate" or unrecognized → escalate path.
        await alert_repo.append_event(
            session,
            alert_id=alert_id,
            tenant_id=tenant_id,
            event_type="hitl_assigned",
            actor_type="agent",
            actor_id="time_anomaly",
            metadata={"reason": "sla_breach"},
        )
        await alert_repo.transition_state(
            session, alert_id=alert_id, new_state="escalated_hitl"
        )
        return {"status": "escalated", "final_state": "escalated_hitl"}
