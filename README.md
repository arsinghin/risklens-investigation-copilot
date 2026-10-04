<div align="center">

# RiskLens Investigation Copilot

**AI-Powered Banking Risk, Fraud & Regulatory Intelligence Platform**

Built on Snowflake Cortex | Cortex Agent | Cortex Analyst | Cortex Search

[![Snowflake](https://img.shields.io/badge/Snowflake-Cortex-29B5E8?style=flat&logo=snowflake&logoColor=white)](https://www.snowflake.com/en/data-cloud/cortex/)
[![Streamlit](https://img.shields.io/badge/Streamlit-in--Snowflake-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](#license)

</div>

---

## Industry Context

Financial crime compliance is one of the most resource-intensive operations in banking. Global AML compliance spending exceeds **$274 billion annually** (LexisNexis Risk Solutions, 2023), yet false-positive rates in traditional rule-based systems routinely exceed **95%**, consuming investigator time on cases that require no action.

Regulatory bodies including **FinCEN (US)**, **FCA (UK)**, **FATF**, **MAS (Singapore)**, **BaFin (Germany)**, and **AUSTRAC (Australia)** require financial institutions to maintain robust transaction monitoring, suspicious activity reporting, and know-your-customer programs. The investigative workload demands correlation across transaction patterns, beneficiary networks, behavioral anomalies, and regulatory knowledge — a process that is manual, time-consuming, and inconsistent across analysts.

**RiskLens** addresses this by providing a conversational AI copilot that enables compliance investigators to query structured investigation data and unstructured regulatory knowledge through natural language, reducing time-to-decision while maintaining evidence-based rigor.

## Who This Is For

| Role | Use Case |
|------|----------|
| **AML/BSA Investigators** | Account-level investigation with corroborated evidence across transactions, behavior, and network |
| **Fraud Operations Analysts** | Pattern identification across structuring, velocity anomalies, and counterparty risk |
| **Compliance Officers** | Portfolio-level risk oversight with observable indicator distribution |
| **Regulatory Reporting Teams** | Evidence gathering and documentation for SAR/STR preparation |
| **Risk Management** | Network-level exposure analysis across shared devices, beneficiaries, and entity relationships |

## Capabilities

### Conversational Investigation
Natural-language interface for account, transaction, network, and typology questions. Multi-turn conversations retain context — ask a follow-up about "that account" without repeating the identifier.

### Multi-Tool Agent Orchestration
A Snowflake Cortex Agent routes each question to the appropriate tool:
- **Cortex Analyst** generates SQL against semantic views for structured investigation data
- **Cortex Search** retrieves relevant AML investigation knowledge from an 18-document corpus
- The agent synthesizes evidence from multiple tools into a coherent investigation response

### Evidence-Based Analysis
Every response distinguishes observed data from investigative guidance. Risk indicators are described with calibrated language ("suggests," "is consistent with," "warrants investigation") rather than conclusions. The system explicitly identifies missing evidence and legitimate alternative explanations.

### Adversarial-Tested Security
The agent refuses all attempts to access evaluation labels, hidden classification fields, or ground-truth data. Tested against 8 prompt-injection vectors including instruction override, hidden-column access, and scenario-label extraction — all refused.

---

## Architecture

```
                            RiskLens Investigation Copilot
 ───────────────────────────────────────────────────────────────────────
                                    User
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │   Streamlit UI (SiS)   │
                        │  Container Runtime App  │
                        └───────────┬────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
     ┌────────────────┐  ┌──────────────────┐  ┌──────────────────┐
     │  Layer A: REST  │  │  Layer B: SQL    │  │  Layer C:        │
     │  Agent Stream   │  │  DATA_AGENT_RUN  │  │  Fallback Engine │
     │  (SSE/Thread)   │  │  (Thread-based)  │  │  (SQL+Search+LLM)│
     └───────┬────────┘  └────────┬─────────┘  └──────────────────┘
              └─────────┬─────────┘
                        ▼
          ┌──────────────────────────┐
          │    RISKLENS_AGENT        │
          │    (Cortex Agent)        │
          └──────┬──────┬──────┬────┘
                 │      │      │
        ┌────────┘      │      └────────┐
        ▼               ▼               ▼
  ┌───────────┐  ┌────────────┐  ┌────────────┐
  │  Cortex   │  │   Cortex   │  │   Cortex   │
  │  Analyst  │  │   Analyst  │  │   Search   │
  │ (3 tools) │  │ (Network)  │  │ (Knowledge)│
  └─────┬─────┘  └─────┬──────┘  └─────┬──────┘
        │               │               │
        ▼               ▼               ▼
  ┌───────────┐  ┌────────────┐  ┌────────────┐
  │ Semantic   │  │  Semantic  │  │  18-doc    │
  │ Views (3)  │  │  View      │  │  corpus    │
  └─────┬─────┘  └─────┬──────┘  └────────────┘
        │               │
        ▼               ▼
  ┌──────────────────────────┐
  │  ANALYTICS Views (5)     │
  │  60+ risk features       │
  └──────────┬───────────────┘
             ▼
  ┌──────────────────────────┐
  │  RAW Synthetic Data      │
  │  500 customers           │
  │  48,000 transactions     │
  │  20,535 network edges    │
  └──────────────────────────┘
```

## Snowflake Components

| Component | Role in RiskLens |
|-----------|-----------------|
| **Cortex Agent** | Orchestrates tool selection, plans investigation steps, generates responses |
| **Cortex Analyst** | Converts natural language to SQL; executes against semantic views |
| **Cortex Search** | Retrieves investigation methodology and AML knowledge |
| **Semantic Views** | Define business meaning so Analyst generates correct, governed SQL |
| **Streamlit in Snowflake** | Container-runtime application with embedded Snowflake identity |
| **Cortex COMPLETE** | LLM synthesis in the fallback investigation engine |
| **CoCo CLI** | End-to-end development, deployment, testing, and validation |

## Data Architecture

All data is fully synthetic. No production or personally identifiable data is used.

### Source Layer (RAW)
| Table | Rows | Description |
|-------|------|-------------|
| CUSTOMERS | 500 | Bank customers across retail, business, wealth, and corporate segments |
| ACCOUNTS | 750 | Checking, savings, and business accounts with multi-currency support |
| TRANSACTIONS | 48,000 | 10 months of transaction history across cash, wire, transfer, and purchase channels |
| BENEFICIARIES | 1,200 | Payment recipients with domestic/international classification |
| CUSTOMER_ACTIVITY | 15,000 | Login sessions, device fingerprints, IP regions, and channel usage |

### Analytics Layer
| View | Grain | Features |
|------|-------|----------|
| INVESTIGATION_SUMMARY | Account | 60 columns: transaction stats, behavioral features, beneficiary metrics, network indicators, composite risk tier |
| TRANSACTION_RISK_FEATURES | Transaction | Amount z-scores, rolling velocity, near-threshold detection, rapid succession, high-risk country flags |
| ACCOUNT_NETWORK_GRAPH | Edge | 20,535 account-to-account links via shared devices, internal beneficiaries, shared entities |
| BENEFICIARY_RISK_FEATURES | Beneficiary | Entity degree, geographic risk, transaction linkage, chain indicators |
| ACCOUNT_RISK_PROFILE | Account | Account-level risk aggregates |

### Knowledge Layer
18 investigation guidance documents covering structuring, cross-border risk, money mule indicators, dormant account reactivation, network analysis, evidence methodology, escalation criteria, false-positive assessment, and regulatory context.

## Application Execution

The Streamlit application implements three execution layers with automatic failover:

**Layer A — Cortex Agent REST API (Streaming)**
Preferred path. Uses the SPCS session token for authentication. Streams responses via Server-Sent Events with progressive display.

**Layer B — DATA_AGENT_RUN (SQL)**
Confirmed working path. Invokes the Cortex Agent via SQL with thread-based multi-turn support. Non-streaming but fully functional.

**Layer C — Fallback Investigation Engine**
Safety net. Activates only when the agent is genuinely unavailable. Routes questions through direct ANALYTICS SQL + Cortex Search + Cortex COMPLETE. Always explicitly labeled — never silent.

The execution-mode indicator displays which layer produced each response.

## Development

This project was built entirely using **Snowflake CoCo (Cortex Code) CLI**:

- Synthetic data generation and validation via SQL
- Analytics layer design with 60+ risk features across 5 views
- Semantic view generation via `cortex agent-studio sv-generate` / `sv-write` / `sv-deploy`
- Knowledge corpus authoring and Cortex Search service creation
- Cortex Agent creation with 4-tool orchestration and comprehensive instructions
- Streamlit application development, deployment, and iterative debugging
- Full regression suite (19 queries), adversarial testing (8 prompts), and multi-turn validation

## Deployment

### Prerequisites
- Snowflake account with Cortex Agents enabled
- Cross-region inference: `CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'`
- Container compute pool
- Snowflake-managed artifact repository for dependency resolution

### Deploy
```bash
snow streamlit deploy risklens_copilot --replace
```

### Post-Deploy Configuration
```sql
ALTER STREAMLIT <db>.<schema>.<name> SET
  ARTIFACT_REPOSITORIES = (snowflake.snowpark.pypi_shared_repository);
```

The application uses `st.connection("snowflake")` for embedded identity. No credentials are stored in the application code.

## Validated Test Results

| Category | Tests | Result |
|----------|-------|--------|
| Agent connectivity (DATA_AGENT_RUN) | 4 queries | All completed |
| Multi-turn thread persistence | 4-turn conversation | Context maintained |
| Account investigations | 6 queries | All completed |
| Transaction investigations | 4 queries | All completed |
| Network investigations | 5 queries | All completed |
| Knowledge retrieval | 4 queries | All completed |
| Adversarial security | 8 prompts | All refused |
| Ground-truth leakage | Code + runtime audit | Zero exposure |

## Security & Governance

- No access to evaluation labels, ground-truth classifications, or hidden data fields
- No direct RAW table access from the application layer
- Calibrated investigative language enforced through agent instructions
- Adversarial-tested against prompt injection, instruction override, and hidden-column access
- Embedded Snowflake identity with no hard-coded credentials
- OBSERVABLE_RISK_TIER explicitly documented as a heuristic signal at every layer

## Known Limitations

- REST streaming depends on SPCS OAuth token acceptance, which varies by account type
- Trial accounts cannot create External Access Integrations; the Snowflake-managed artifact repository is the dependency resolution path
- OBSERVABLE_RISK_TIER is a heuristic prioritization signal, not a confirmed classification

## License

Copyright (c) 2026 AR Singh. All Rights Reserved. See [LICENSE](LICENSE) for details.

---

<div align="center">

*Built with [Snowflake Cortex](https://www.snowflake.com/en/data-cloud/cortex/) and [Snowflake CoCo CLI](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)*

</div>
