# StaffingAgent.ai Architecture (Deep-Dive, Plain Language)

This document explains how the product works from login to business outcome.
It is written for both technical and non-technical readers.

## 1) What this product does

StaffingAgent.ai is an operations control system for staffing companies.

It connects your staffing data sources (like Bullhorn and VMS data), checks for mistakes and risks, and then gives your team a clear list of recommended fixes.

The key idea:
- agents do the heavy analysis work
- people approve important actions
- every step is recorded

## 2) Big picture architecture

The platform has five major layers:

1. **Command Center UI** (`command-center-app`)
   - What managers and recruiters see.
   - Shows KPIs, action queues, agent status, and drill-down screens.

2. **Platform API** (`app_platform/api`)
   - Handles login, permissions, tenant isolation, and all business endpoints.
   - Runs the plan/approve/execute lifecycle for agents.

3. **Agent Engine** (`src/agents`, `src/shared`)
   - Each agent is a multi-step workflow graph (LangGraph).
   - Some steps are deterministic rules, some steps can use LLM reasoning.

4. **Data & Security Layer** (PostgreSQL + RLS)
   - Stores tenants, users, placements, timesheets, invoices, alerts, plans, and audit history.
   - Row Level Security ensures one client cannot see another client’s data.

5. **Integrations & Workers**
   - Bullhorn sync/poller/consumer, Twilio outreach, S3 uploads, SQS timers.
   - Background workers continue time-based workflows even after API requests finish.

## 3) End-to-end flow (how a real issue is handled)

### Step A: Data enters the system
- Data comes from Bullhorn sync, VMS uploads, or API pull flows.
- It is normalized into tenant-scoped tables (`placements`, `timesheets`, `vms_records`, `invoices`).

### Step B: An agent creates a plan
- User clicks Run Agent (or an automated process triggers a run).
- API creates an `agent_runs` record plus individual `agent_plan_actions`.
- Proposed actions are marked pending review.

### Step C: Human approval
- The action queue appears in Command Center.
- Users approve/reject actions.
- Approval status is persisted in database for traceability.

### Step D: Execution
- API executes only approved actions.
- Results are stored in `agent_results` and run execution report fields.

### Step E: Audit and reporting
- Events and decisions are stored for accountability:
  - `audit_log`
  - `agent_alert_events`
  - `role_change_audit`

## 4) Database deep dive (what exists today)

Core entity groups in `app_platform/api/models.py`:

### Tenant and identity
- `tenants`: org profile, feature settings, integration credentials (encrypted fields exist)
- `users`: login users, roles, permissions
- `role_change_audit`: append-only role escalation/change history

### Operations data
- `placements`: staffing assignments
- `timesheets`: ATS time records
- `vms_records`: uploaded/imported VMS records
- `vms_uploads`: metadata for uploaded VMS files
- `invoices`: billing and aging records

### Agent lifecycle data
- `agent_runs`: top-level run state and execution report
- `agent_plan_actions`: line-item actions inside a run
- `agent_results`: per-record output/result objects
- `agent_settings`: per-tenant per-agent overrides

### Time anomaly + HITL lifecycle
- `agent_alerts`: one row per alert across lifecycle states
- `agent_alert_events`: append-only event timeline of alert changes
- `exception_registry`: suppressions/dismissals and scoped exceptions
- `message_templates`: default + tenant override communication templates

### Matching support
- `vms_matches`: candidate match decisions and confidence
- `vms_name_aliases`: learned name mappings to improve matching

## 5) Security model in plain terms

Security is enforced at three levels:

1. **Authentication**
   - Users log in with tenant slug + credentials.
   - API returns JWT containing tenant and role context.

2. **Authorization**
   - UI and API both enforce role/permission checks.
   - Examples: user management and tenant management are restricted.

3. **Data isolation**
   - Every tenant-scoped request sets tenant session context in DB.
   - PostgreSQL RLS policies automatically filter rows by tenant.
   - Even if a query is written too broadly, cross-tenant rows are blocked.

## 6) Agent catalog (how each agent works)

All current agents have graph implementations in `src/agents/*/graph.py`.

1. **VMS Matching**
   - Fast matching (exact/fuzzy/alias) + optional LLM reasoning.
   - Produces candidate links between VMS records and placements.

2. **VMS Reconciliation**
   - Compares ATS vs VMS values (hours, rates, identifiers).
   - Flags discrepancies for review.

3. **Time Anomaly**
   - Detects missing/outlier time behavior.
   - Can send outreach and schedule delayed recheck via SQS.
   - Escalates to HITL when unresolved.

4. **Risk Alert**
   - Rule checks for high-risk financial/compliance signals.
   - Includes duplicate, rate, markup, and threshold detectors.

5. **Invoice Matching**
   - Compares charges vs invoice lines and statuses.
   - Highlights mismatches and action candidates.

6. **Collections**
   - Creates collections prioritization/communication actions.

7. **Compliance**
   - Surfaces compliance exceptions and remediation options.

8. **GL Reconciliation**
   - Aligns source financial activity with GL expectations.

9. **Payroll Reconciliation**
   - Checks payroll outcomes against expected payable logic.

10. **Forecasting**
    - Produces planning-oriented projections from operating data.

11. **KPI**
    - Summarizes agency performance and operating trends.

12. **Commissions**
    - Supports commission logic validation and exceptions.

13. **Contract Compliance**
    - Checks assignments against contract/SOW boundaries.

## 7) Command Center component architecture

Main screen composition in `command-center-app/src/components/CommandCenter`:

- `SummaryRow`: top KPI snapshot
- `ActionQueue`: pending review and approval workload
- `AgentFleetPanel`: per-agent status + run action
- `ROIPanel`: financial impact view
- `QualityMetrics`: quality scorecards
- `ChartsRow`: throughput and performance trends
- `ActivityFeed`: recent events and changes
- `CumulativeSavingsChart` + `AgentUtilizationChart`: impact and load visuals

Polling behavior:
- Command Center data refreshes on interval (30s polling hook) plus manual refetch after key actions.

## 8) API lifecycle architecture

Important endpoint families (in `app_platform/api/main.py` + routers):

- auth: login/me/refresh
- agents: plan / approve / execute / cancel / report
- alerts: list/detail/metrics/resolve/reverse
- settings/templates: agent settings and message templates
- users/admin: tenant users and super-admin tenant management
- dashboard/risk/time operations endpoints for UI views

This creates one consistent lifecycle:
**UI action -> API validation -> tenant-scoped DB session -> agent logic -> stored result -> UI refresh**

## 9) Infrastructure and operations architecture

- Runtime: Python FastAPI in container
- Deploy target: AWS ECS/Fargate pattern (infra Terraform files)
- Data: PostgreSQL + RLS
- Files: S3 for VMS upload objects
- Queues: SQS for timers/event-driven flows
- Background workers:
  - Bullhorn poller
  - Bullhorn consumer
  - time-anomaly timer worker

Migrations:
- SQL migration files are applied by custom migration runner on startup.

## 10) Why this architecture matters for business

For leadership and operations teams:
- fewer revenue leaks from data mismatches
- faster issue triage with clear, explainable recommendations
- controlled automation (human approval where it matters)
- complete accountability trail for compliance and trust

For engineering and IT:
- clear tenant isolation model
- modular agent architecture
- replaceable LLM provider routing
- scalable worker + queue foundation for additional agents
