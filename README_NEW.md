# StaffingAgent.ai — The Intelligent Staffing Platform

[![Tech Stack](https://img.shields.io/badge/Stack-FastAPI%20|%20React%20|%20LangGraph-blue)](https://staffingagent.ai)
[![Security](https://img.shields.io/badge/Security-Multi--Tenant%20RLS-green)](https://staffingagent.ai)

StaffingAgent.ai is a production-grade AI platform that automates back-office staffing operations. By combining **LangGraph** orchestration with a multi-provider **Smart Model Router**, the platform deploys specialized agents that catch financial leaks, reconcile VMS data, and audit payroll with human-level reasoning and machine-level speed.

---

## 🏗️ Project Architecture

For a deep dive into the technical design, security model, and agentic state machines, see [**ARCHITECTURE_NEW.md**](ARCHITECTURE_NEW.md).

### Core Components
- **`/app_platform`**: FastAPI backend with Multi-Tenant Row Level Security (RLS).
- **`/command-center-app`**: High-performance React dashboard for agent monitoring and HITL intervention.
- **`/src/agents`**: Specialized LangGraph implementations (Time Anomaly, VMS Matching, etc.).
- **`/src/shared`**: Cross-cutting concerns: Smart LLM Router, Tier Enforcement, and Audit Logging.
- **`/deploy`**: Production-ready infrastructure (AWS/Docker) and DB migrations.

---

## 🤖 The Agent Fleet

The platform currently supports 12 specialized agent modules, categorized by operational phase:

### Phase 0: Core Operations
- **Time Anomaly:** Detects missing/duplicate/extreme hours.
- **VMS Matching:** Reconciles external VMS portals with internal ATS records.
- **Compliance:** Audits placement data against state/federal requirements.

### Phase 1: Financial & Advanced
- **GL Recon:** Automated General Ledger reconciliation.
- **Payroll Auditor:** Catches variances before money leaves the bank.
- **Collections:** Prioritizes AR aging and drafts outreach.

---

## 🚦 Quick Start for Developers

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 15+ (with `pgcrypto` and `uuid-ossp`)

### 2. Backend Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Environment Setup
cp .env.example .env
# Set DATABASE_URL, ANTHROPIC_API_KEY, etc.

# Run migrations & start server
uvicorn app_platform.api.main:app --reload
```

### 3. Frontend Setup
```bash
cd command-center-app
npm install
npm run dev
```

---

## 📈 Business Value & ROI
For a non-technical guide on how the product works and how to use the Command Center, see [**PRODUCT_GUIDE.md**](PRODUCT_GUIDE.md).

- **Recovered Revenue:** Eliminates unbilled time lost in VMS discrepancies.
- **Error Reduction:** Catch 99% of payroll variances before they occur.
- **Scale:** Manage 10,000+ placements with a skeleton back-office team.

---

## 🔒 Security & Compliance
- **SOC2 Ready:** Full audit trails for every AI decision.
- **Encryption:** Bullhorn credentials are encrypted at rest using AES-256-GCM.
- **Data Privacy:** Hard multi-tenant isolation via PostgreSQL RLS.

---
© 2026 StaffingAgent LLC. All rights reserved.
