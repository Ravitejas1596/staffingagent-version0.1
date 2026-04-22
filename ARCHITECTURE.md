# StaffingAgent.ai — Agent Architecture

This document describes the agent architecture built in this repo, aligned to **StaffingAgent_Strategic_Plan_v4** and the five-pillar product model.

## Strategic Context

- **Product:** AI transformation platform for mid-to-large staffing ($100M–$1B+).
- **Pillar 3 (AI Agent Deployment):** Purpose-built staffing agents with **human-in-the-loop**.
- **Tech stack (from plan):** LangGraph, Anthropic Claude, nBrain (KB), Bullhorn REST, AWS, custom API gateway.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     StaffingAgent Platform                        │
├─────────────────────────────────────────────────────────────────┤
│  API Gateway (src/api)                                           │
│  - Abstracts nBrain (KB) and Bullhorn (ATS)                     │
│  - Tenant config; token passthrough / billing hooks              │
├─────────────────────────────────────────────────────────────────┤
│  Agents (src/agents) — LangGraph + Claude                        │
│  - VMS Reconciliation   - Invoice Matching   - Time Anomaly      │
│  - Collections          - Compliance                            │
│  Each: analyze node → optional human_review node → result       │
├─────────────────────────────────────────────────────────────────┤
│  Shared (src/shared)                                             │
│  - State types (per-agent)  - Claude client + token usage        │
│  - HITL node pattern       - Base graph helpers                  │
└─────────────────────────────────────────────────────────────────┘
```

## Agent Pattern

Every agent follows the same pattern:

1. **State** — Pydantic model extending `AgentState` with agent-specific fields (e.g. `vms_records`, `proposed_matches`).
2. **Analyze node** — Calls Claude with a system prompt and current state; returns proposed outputs and sets `human_review_required` when confidence is low or policy requires approval.
3. **Human review node** — Placeholder that sets `human_review_required`; in production this would enqueue a task for a human and resume when the human submits a decision.
4. **Conditional edge** — After analyze: go to `human_review` if `human_review_required` else END.
5. **Token usage** — Every Claude call appends to `state["token_usage"]` for passthrough billing (actual + 30%).

## Purpose-Built Agents

| Agent | Input state keys | Output / result | HITL when |
|-------|------------------|-----------------|-----------|
| **VMS Reconciliation** | `vms_records`, `ats_records` | `proposed_matches`, `unmatched_*`, `summary` | confidence < 0.9 or ambiguous |
| **Invoice Matching** | `purchase_orders`, `invoices` | `proposed_matches`, `exceptions`, `summary` | exceptions or confidence < 0.95 |
| **Time Anomaly** | `time_entries` | `anomalies`, `suggested_corrections`, `summary` | high severity or correction approval |
| **Collections** | `ar_aging` | `prioritization`, `suggested_actions`, `draft_messages`, `summary` | escalation or message approval |
| **Compliance** | `policies`, `activity_log` | `violations`, `recommended_actions`, `summary` | high-severity violation or exception |

## Data Flow (Production)

1. **Data source** — Records come from the API gateway: `gateway.get_vms_records(tenant_id)`, `gateway.get_ats_records(tenant_id)`, or equivalent for other agents. Gateway talks to nBrain (if needed for context) and Bullhorn/VMS per tenant config.
2. **Invocation** — API or internal job passes initial state into the compiled LangGraph; graph runs until END or human_review.
3. **HITL** — When `human_review_required` is true, the runtime enqueues a task; when the human submits a decision, `apply_human_decision(state, decision)` is called and the graph can resume or complete.
4. **Result** — `state["result"]` and `state["token_usage"]` are persisted for ROI reporting and billing.

## Config and Multi-Tenant

- **config/tenant_example.json** — Schema for tenant config: nBrain/Bullhorn flags and env var names, which agents are enabled.
- Secrets (API keys, Bullhorn credentials) live in env or vault, not in repo.
- Each agent receives `tenant_id` in state; the API gateway resolves credentials and endpoints by tenant.

## Cursor as Internal Operating Platform

Per the strategic plan, StaffingAgent uses **Cursor** as the primary internal platform for:

- **Agent development** — This repo: LangGraph graphs, prompts, and shared code.
- **Internal automation** — Cursor agents for docs, codegen, integration work.
- **Knowledge management** — Single codebase and config for all customer deployments.

The AI Architect (and Cursor) extend this repo with:

- Real nBrain and Bullhorn integrations in `src/api/gateway.py`.
- Production HITL (queue + UI) replacing the placeholder `human_review_node`.
- Deployment (e.g. AWS Lambda + API Gateway, or containers) and tenant onboarding.

## References

- **StaffingAgent_Strategic_Plan_v4.docx** — Business model, five pillars, pricing, tech stack, Cursor bet.
- **GHR use case (seed-knowledge-base.json)** — VMS reconciliation (B4Health ↔ Bullhorn), unbilled backlog; same pattern for other agents.
- **StaffingAgent_AI_Training_Document_v4.pdf** — When available in workspace, use for prompt refinement and runbooks.
