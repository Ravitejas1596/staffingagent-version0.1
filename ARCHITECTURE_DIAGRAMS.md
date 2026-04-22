# StaffingAgent.ai - Architecture Diagrams (Deep Dive)

These diagrams mirror how the current codebase is organized and how the product behaves in production.

## 1) End-to-End System Map

```mermaid
flowchart LR
    U[Operations User] --> CC[Command Center Web App]
    CC --> API[FastAPI Platform API]

    subgraph Core Platform
      API --> AUTH[Auth and Permissions]
      API --> ORCH[Agent Orchestration]
      ORCH --> GRAPH[LangGraph Agent Graphs]
      API --> DB[(PostgreSQL with RLS)]
      API --> S3[(S3 VMS Uploads)]
      API --> SQS[(SQS Queues)]
    end

    GRAPH --> ROUTER[LLM Router]
    ROUTER --> CLAUDE[Anthropic]
    ROUTER --> OPENAI[OpenAI]
    ROUTER --> GEMINI[Google Gemini]

    API --> BULLHORN[Bullhorn ATS]
    API --> VMS[VMS Data and Uploads]
    API --> TWILIO[Twilio SMS]

    SQS --> WORKER1[Time Anomaly Timer Worker]
    SQS --> WORKER2[Bullhorn Consumer Worker]
```

## 2) Agent Plan-Approve-Execute Lifecycle

```mermaid
sequenceDiagram
    participant User as Operator
    participant UI as Command Center
    participant API as Platform API
    participant DB as PostgreSQL
    participant AG as Agent Graph

    User->>UI: Click Run Agent
    UI->>API: POST /agents/{type}/plan
    API->>AG: Build plan from data
    AG-->>API: Suggested actions
    API->>DB: Save agent_runs and agent_plan_actions
    API-->>UI: Plan ready

    User->>UI: Approve selected actions
    UI->>API: POST /agents/{type}/approve
    API->>DB: Mark approved actions
    API-->>UI: Approved

    User->>UI: Execute
    UI->>API: POST /agents/{type}/execute
    API->>AG: Execute approved actions
    API->>DB: Save results and execution report
    API-->>UI: Completed report
```

## 3) Time Anomaly Stateful Workflow

```mermaid
stateDiagram-v2
    [*] --> Detect
    Detect --> Outreach: anomaly found
    Outreach --> WaitForRecheck: SMS/reminder sent
    WaitForRecheck --> Resolved: issue corrected
    WaitForRecheck --> EscalateHITL: still unresolved
    EscalateHITL --> HumanDecision
    HumanDecision --> ExecuteFix: approved
    HumanDecision --> Dismissed: rejected
    ExecuteFix --> Closed
    Resolved --> Closed
    Dismissed --> Closed
    Closed --> [*]
```

## 4) Tenant Security Boundary (RLS)

```mermaid
sequenceDiagram
    participant A as Tenant A User
    participant API as API
    participant DB as PostgreSQL + RLS
    participant B as Tenant B User

    A->>API: Request with Tenant A JWT
    API->>DB: set app.tenant_id = A
    DB-->>API: only Tenant A rows
    API-->>A: Tenant A data

    B->>API: Request with Tenant B JWT
    API->>DB: set app.tenant_id = B
    DB-->>API: only Tenant B rows
    API-->>B: Tenant B data
```

## 5) Command Center Component Layout

```mermaid
flowchart TB
    CC[Command Center Screen]
    CC --> S[Summary Row]
    CC --> Q[Action Queue]
    CC --> F[Agent Fleet Panel]
    CC --> R[ROI Panel]
    CC --> M[Quality Metrics]
    CC --> C[Charts Row]
    CC --> A[Activity Feed]
    CC --> CS[Cumulative Savings Chart]
    CC --> U[Agent Utilization Chart]
```

## 6) Data Ingestion and Processing

```mermaid
flowchart LR
    BH[Bullhorn Poller] --> QUEUE[SQS Event Queue]
    QUEUE --> CONSUMER[Consumer Worker]
    CONSUMER --> DB[(PostgreSQL)]

    UPLOAD[VMS File Upload] --> S3[(S3 Bucket)]
    S3 --> API[Platform API]
    API --> DB

    DB --> AGENTS[Agent Graphs]
    AGENTS --> ALERTS[Alerts and Plans]
    ALERTS --> UI[Command Center]
```
