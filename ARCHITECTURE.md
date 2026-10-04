# RiskLens Architecture

## System Layers

### Layer 1 — RAW (Synthetic Data)
Five tables in `RISKLENS.RAW` containing fully synthetic banking data:
- **CUSTOMERS** (500) — Demographics, segments, risk tiers, countries
- **ACCOUNTS** (750) — Account types, currencies, statuses, opening dates
- **TRANSACTIONS** (48,000) — 10 months of transactions with amounts, channels, counterparties, countries
- **BENEFICIARIES** (1,200) — Payment recipients with relationship metadata
- **CUSTOMER_ACTIVITY** (15,000) — Login sessions, devices, IP regions, channels

Nine behavioral populations are embedded: NORMAL, STRUCTURING, CROSS_BORDER, AMOUNT_ANOMALY, LEGIT_HIGH_VALUE, DORMANT_ACTIVATION, MULE, CIRCULAR, and SHARED. These produce realistic investigation patterns without being directly observable.

### Layer 2 — ANALYTICS (Risk Feature Views)
Five views in `RISKLENS.ANALYTICS`:
- **INVESTIGATION_SUMMARY** (718 rows, 60 columns) — One row per account with transaction stats, behavioral features, beneficiary metrics, network indicators, and OBSERVABLE_RISK_TIER
- **TRANSACTION_RISK_FEATURES** (48,000 rows) — Per-transaction risk signals: amount z-scores, rolling velocity, near-threshold flags, rapid succession, high-risk country indicators
- **ACCOUNT_NETWORK_GRAPH** (20,535 edges) — Account-to-account links via shared devices (587), internal beneficiaries (29), and shared entities (19,919)
- **BENEFICIARY_RISK_FEATURES** (1,200 rows) — Per-beneficiary risk: entity degree, transaction linkage, geographic risk, chain indicators
- **ACCOUNT_RISK_PROFILE** (718 rows) — Account-level aggregates

OBSERVABLE_RISK_TIER distribution: NONE=26, LOW=96, MEDIUM=393, HIGH=203.

### Layer 3 — SEMANTIC (Cortex Analyst Views)
Three semantic views in `RISKLENS.SEMANTIC`:
- **ACCOUNT_INVESTIGATION** — Over INVESTIGATION_SUMMARY, 6 verified queries
- **TRANSACTION_INVESTIGATION** — Over TRANSACTION_RISK_FEATURES
- **NETWORK_INVESTIGATION** — Over ACCOUNT_NETWORK_GRAPH + BENEFICIARY_RISK_FEATURES

### Layer 4 — KNOWLEDGE (Cortex Search)
- **KNOWLEDGE_CORPUS** (18 documents) — AML investigation guidance covering structuring, cross-border, mule indicators, evidence methodology, escalation criteria, false positives, and more
- **INVESTIGATION_SEARCH** — Cortex Search service over the corpus with CONTENT (searchable), CATEGORY (filterable), TITLE (searchable + filterable)

### Layer 5 — PUBLIC (Agent + Evaluation)
- **RISKLENS_AGENT** — Cortex Agent with 4 tools:
  - AccountInvestigation (Cortex Analyst)
  - TransactionInvestigation (Cortex Analyst)
  - NetworkInvestigation (Cortex Analyst)
  - InvestigationKnowledge (Cortex Search)
- **GROUND_TRUTH_SCENARIOS** — Evaluation-only view (never exposed through the agent or application)

### Layer 6 — STREAMLIT (Application)
- **RISKLENS_COPILOT** — Container-runtime Streamlit application with three-layer execution:
  1. REST API streaming (Layer A)
  2. DATA_AGENT_RUN SQL (Layer B — confirmed working)
  3. Fallback engine (Layer C — direct SQL + Search + COMPLETE)

## Data Flow

```
User Question
     |
     v
Streamlit Chat Interface
     |
     v
Execution Layer Selection (REST → SQL → Fallback)
     |
     v
RISKLENS_AGENT (Cortex Agent)
     |
     +---> Cortex Analyst  ---> Semantic View ---> ANALYTICS View ---> RAW Tables
     |
     +---> Cortex Search   ---> KNOWLEDGE_CORPUS
     |
     v
Agent Orchestration (tool selection, SQL generation, response synthesis)
     |
     v
Structured Response + Evidence
     |
     v
Streamlit Chat Display (with execution mode indicator)
```

## Leakage Prevention

The system enforces strict separation between investigation tools and evaluation data:

- BENEFICIARIES.PATTERN is never exposed in ANALYTICS, SEMANTIC, or KNOWLEDGE layers
- GROUND_TRUTH_SCENARIOS is never referenced by the agent instructions, tool resources, or application code
- OBSERVABLE_RISK_TIER is explicitly documented as a heuristic prioritization signal in the agent instructions, semantic view comments, knowledge corpus, and application UI
- The agent's orchestration instructions explicitly prohibit querying ground-truth objects
- The Streamlit application code contains zero references to ground-truth tables or pattern fields
