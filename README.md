# RiskLens Investigation Copilot

Banking Risk, Fraud & Regulatory Intelligence Copilot powered by Snowflake Cortex.

## Problem Statement

Financial institutions must investigate thousands of accounts for potential money laundering, fraud, and regulatory violations. Investigators need to correlate transaction patterns, beneficiary networks, behavioral anomalies, and regulatory knowledge to make evidence-based decisions — a process that is manual, time-consuming, and prone to inconsistency.

## Target Users

Banking compliance analysts, AML investigators, and fraud operations teams who need a conversational interface to investigate accounts using structured data and unstructured knowledge together.

## Key Capabilities

- **Conversational investigation** — Ask natural-language questions about accounts, transactions, networks, and AML methodology
- **Multi-tool orchestration** — The Cortex Agent routes questions to the right tool: Cortex Analyst for structured data, Cortex Search for investigation knowledge
- **Multi-turn context** — Thread-based conversations maintain context across follow-up questions
- **Evidence presentation** — Structured data results and knowledge sources are presented alongside natural-language analysis
- **Calibrated language** — The agent uses investigation-appropriate language ("suggests," "warrants investigation") rather than conclusions
- **Leakage prevention** — No access to ground-truth labels, evaluation datasets, or hidden classification fields

## Architecture

```
User
  |
  v
Streamlit UI (SiS Container Runtime)
  |
  |--- Layer A: Cortex Agent REST API (streaming SSE) [preferred]
  |--- Layer B: DATA_AGENT_RUN (SQL, non-streaming)   [confirmed working]
  |--- Layer C: Fallback Engine (SQL + Search + LLM)   [safety net]
  |
  v
RISKLENS.PUBLIC.RISKLENS_AGENT (Cortex Agent)
  |
  |--- AccountInvestigation    (Cortex Analyst -> ACCOUNT_INVESTIGATION semantic view)
  |--- TransactionInvestigation (Cortex Analyst -> TRANSACTION_INVESTIGATION semantic view)
  |--- NetworkInvestigation     (Cortex Analyst -> NETWORK_INVESTIGATION semantic view)
  |--- InvestigationKnowledge   (Cortex Search  -> INVESTIGATION_SEARCH service)
  |
  v
Analytics Views (RISKLENS.ANALYTICS)
  |--- INVESTIGATION_SUMMARY          (718 accounts, 60 columns)
  |--- TRANSACTION_RISK_FEATURES      (48,000 transactions)
  |--- ACCOUNT_NETWORK_GRAPH          (20,535 edges)
  |--- BENEFICIARY_RISK_FEATURES      (1,200 beneficiaries)
  |--- ACCOUNT_RISK_PROFILE           (718 accounts)
  |
  v
RAW Synthetic Data (RISKLENS.RAW)
  |--- CUSTOMERS           (500)
  |--- ACCOUNTS            (750)
  |--- TRANSACTIONS        (48,000)
  |--- BENEFICIARIES       (1,200)
  |--- CUSTOMER_ACTIVITY   (15,000)
```

## Snowflake Components Used

| Component | Purpose |
|-----------|---------|
| **Cortex Agent** | Orchestrates tool selection and response generation |
| **Cortex Analyst** | Converts natural language to SQL against semantic views |
| **Cortex Search** | Retrieves AML investigation knowledge from an 18-document corpus |
| **Semantic Views** | Define business meaning for tables so Analyst generates correct SQL |
| **Streamlit in Snowflake** | Container-runtime application deployment |
| **Cortex COMPLETE** | LLM synthesis in the fallback engine |

## CoCo CLI Usage

This project was built entirely using Snowflake CoCo (Cortex Code) CLI:

- **Data generation** — Synthetic RAW tables created via SQL through CoCo
- **Analytics layer** — 5 views with 60+ risk features designed and validated through CoCo
- **Semantic views** — Generated via `cortex agent-studio sv-generate` / `sv-write` / `sv-deploy`
- **Knowledge corpus** — 18 investigation documents created and loaded through CoCo
- **Cortex Agent** — Created via `CREATE AGENT` with 4 tools and comprehensive orchestration instructions
- **Streamlit app** — Written, deployed, and debugged entirely through CoCo
- **Testing** — All regression, security, and multi-turn tests executed through CoCo

## Synthetic Dataset

All data is fully synthetic. No production or PII data is used.

| Table | Rows | Description |
|-------|------|-------------|
| CUSTOMERS | 500 | Synthetic bank customers across segments |
| ACCOUNTS | 750 | Checking, savings, business accounts |
| TRANSACTIONS | 48,000 | 10 months of transaction history with behavioral patterns |
| BENEFICIARIES | 1,200 | Payment recipients with relationship metadata |
| CUSTOMER_ACTIVITY | 15,000 | Login, session, device, and channel activity |

The dataset contains 9 behavioral populations designed to produce realistic investigation scenarios, including normal activity, structuring patterns, cross-border indicators, amount anomalies, dormant reactivation, and network relationships.

## How the Streamlit App Works

The application implements a three-layer execution architecture:

1. **Layer A — Cortex Agent REST API**: Attempts streaming SSE connection using the SPCS session token. Provides progressive response display.

2. **Layer B — DATA_AGENT_RUN (SQL)**: The confirmed working path. Calls `SNOWFLAKE.CORTEX.DATA_AGENT_RUN()` with thread support for multi-turn conversations. The agent orchestrates across its 4 tools and returns structured responses.

3. **Layer C — Fallback Engine**: Activates only when the agent is unavailable. Uses direct SQL against analytics views + Cortex Search + Cortex COMPLETE. Always explicitly labeled — never silent.

The execution mode indicator displays which layer produced each response.

## Demo Workflow

See [DEMO.md](DEMO.md) for the complete demo script with exact questions and expected investigation flow.

## Deployment

### Prerequisites
- Snowflake account with Cortex Agents enabled
- `CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'`
- Container compute pool (e.g., `SYSTEM_COMPUTE_POOL_CPU`)
- Snowflake-managed artifact repository for dependency resolution

### Deploy
```bash
snow streamlit deploy risklens_copilot --replace
```

### Configuration
The `snowflake.yml` manifest targets the container runtime (`SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`). The app uses `st.connection("snowflake")` for embedded identity — no credentials are stored in the application.

The Streamlit object requires:
```sql
ALTER STREAMLIT <db>.<schema>.<name> SET
  ARTIFACT_REPOSITORIES = (snowflake.snowpark.pypi_shared_repository);
```

## Known Limitations

- **REST streaming**: The SPCS OAuth token may not be accepted by the Cortex Agent REST endpoint on all account types. Layer B (DATA_AGENT_RUN) is the confirmed fallback.
- **Trial accounts**: Cannot create External Access Integrations. The Snowflake-managed artifact repository (`snowflake.snowpark.pypi_shared_repository`) is the workaround for dependency resolution.
- **OBSERVABLE_RISK_TIER**: This is a heuristic investigation-prioritization signal based on observable indicators. It is not ground truth, not a confirmed suspicious classification, and not a model prediction.

## Security & Governance

- **No ground-truth exposure**: The application never queries `GROUND_TRUTH_SCENARIOS` or exposes evaluation labels
- **No pattern leakage**: `BENEFICIARIES.PATTERN` is never accessible through the agent or fallback engine
- **No RAW table access**: The application queries only ANALYTICS views, never RAW tables directly
- **Calibrated language**: The agent uses "suggests," "indicates," "warrants investigation" — never definitive conclusions
- **Adversarial resistance**: Tested against 8 prompt-injection attempts (ground truth requests, instruction override, hidden column access) — all correctly refused
- **Embedded identity**: No hard-coded credentials; uses Snowflake's built-in SiS authentication

## License

This project was created for the Snowflake CoCo CLI Hackathon. All data is synthetic.
