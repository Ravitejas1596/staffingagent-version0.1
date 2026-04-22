# StaffingAgent.ai - Final Product Readme

This README explains the product in simple language first, then links core technical concepts for implementation teams.

## What this product is

StaffingAgent.ai is a command center for staffing operations.

It continuously checks data across placements, timesheets, VMS records, payroll, billing, and invoices, then recommends actions to fix issues before they become revenue, compliance, or trust problems.

## What makes it different

- It is **agent-based** (specialists per workflow, not one monolithic bot).
- It is **human-controlled** (important actions can require approval).
- It is **tenant-safe** (strict client isolation in database access).
- It is **operationally practical** (real dashboards, queues, settings, and audit history).

## Product capabilities at a glance

- Command Center dashboard with operational and financial KPIs
- Action Queue for review/approval workflows
- Agent run lifecycle: plan -> approve -> execute -> report
- Alert lifecycle with event history and reversible actions
- Multi-tenant user and client administration
- Per-agent settings and messaging templates

## Core agent families

The codebase currently includes:
- Time Anomaly
- Risk Alert
- Invoice Matching
- Collections
- Compliance
- VMS Reconciliation
- VMS Matching
- GL Reconciliation
- Payroll Reconciliation
- Forecasting
- KPI
- Commissions
- Contract Compliance

Each follows the same operating pattern:
1. inspect tenant data
2. detect issues/opportunities
3. create action plan
4. wait for required approvals
5. execute approved actions
6. record results and audits

## How the Command Center maps to workflow

- **Summary Row**: quick health check of current operation
- **Action Queue**: pending decisions and workload
- **Agent Fleet**: run/status control of each agent
- **ROI and Quality**: impact and confidence indicators
- **Charts and Feed**: trends and recent events

The Command Center updates on interval polling for live operations visibility.

## Database and security model

Primary operational tables include:
- tenants and users
- placements, timesheets, vms_records, invoices
- agent_runs, agent_plan_actions, agent_results
- agent_alerts, agent_alert_events, exception_registry
- agent_settings, message_templates, audit_log

Security model:
- JWT-based authentication
- role/permission checks
- PostgreSQL Row Level Security (RLS) for tenant data isolation

## Integrations and background processing

External integrations include:
- Bullhorn ATS
- VMS uploads/records
- Twilio (outreach)
- S3 (file storage)
- SQS (timers/event queues)
- optional LLM providers via smart routing (Anthropic, OpenAI, Gemini)

Background services include:
- Bullhorn poller
- Bullhorn consumer
- time anomaly timer worker

## Key architecture docs

- `ARCHITECTURE_NEW.md` - full architecture walkthrough
- `ARCHITECTURE_DIAGRAMS.md` - visual architecture and flow diagrams
- `PRODUCT_GUIDE.md` - operator-focused product guide

## Audience-specific quick summary

- **For operations teams**: this helps you catch and fix issues faster with clear recommendations.
- **For executives**: this reduces leakage, improves process control, and provides measurable impact.
- **For engineering/IT**: this is a modular FastAPI + LangGraph + PostgreSQL multi-tenant platform with workers and clear extension points.
