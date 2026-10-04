"""
RiskLens Investigation Copilot — Streamlit Application
Banking Risk, Fraud & Regulatory Intelligence Interface

Execution layers:
  A) Cortex Agent REST API (streaming SSE) — preferred
  B) DATA_AGENT_RUN (SQL, non-streaming) — secondary
  C) Fallback Investigation Engine (direct SQL + Search + COMPLETE)
"""

import streamlit as st
import json
import re
import os
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("risklens")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="RiskLens Investigation Copilot",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        font-size: 1.6rem; font-weight: 700; color: #E8E8E8;
        padding-bottom: 0.5rem; border-bottom: 2px solid #1B4F72; margin-bottom: 0.3rem;
    }
    .sub-header {
        font-size: 0.85rem; color: #8899AA; margin-top: -0.5rem; margin-bottom: 0.5rem;
    }
    .exec-mode {
        font-size: 0.75rem; padding: 0.2rem 0.6rem; border-radius: 4px;
        display: inline-block; margin-bottom: 1rem;
    }
    .exec-rest { background: #1a3a2a; color: #27AE60; border: 1px solid #27AE60; }
    .exec-sql { background: #1a2a3a; color: #3498DB; border: 1px solid #3498DB; }
    .exec-fallback { background: #3a2a1a; color: #F39C12; border: 1px solid #F39C12; }
    .status-ok { color: #27AE60; }
    .status-warn { color: #F39C12; }
    .status-err { color: #E74C3C; }
    .stButton > button { text-align: left; font-size: 0.82rem; }
    .stDataFrame { font-size: 0.85rem; }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        font-size: 0.9rem; color: #8899AA; text-transform: uppercase; letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# LAYER 0: Snowflake SQL connection
# ===========================================================================
@st.cache_resource
def get_connection():
    return st.connection("snowflake")


def run_query(sql, params=None):
    return get_connection().query(sql, params=params)


# ===========================================================================
# LAYER A: Cortex Agent REST API (streaming SSE)
# ===========================================================================
AGENT_DB = "RISKLENS"
AGENT_SCHEMA = "PUBLIC"
AGENT_NAME = "RISKLENS_AGENT"
AGENT_FQN = f"{AGENT_DB}.{AGENT_SCHEMA}.{AGENT_NAME}"
AGENT_REST_PATH = f"/api/v2/databases/{AGENT_DB}/schemas/{AGENT_SCHEMA}/agents/{AGENT_NAME}:run"
THREAD_CREATE_PATH = "/api/v2/cortex/threads"


def _get_spcs_token():
    try:
        with open("/snowflake/session/token", "r") as f:
            return f.read().strip() or None
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _get_snowflake_host():
    return os.getenv("SNOWFLAKE_HOST")


def rest_api_available():
    return _get_spcs_token() is not None and _get_snowflake_host() is not None


def _rest_headers():
    return {
        "Authorization": f"Bearer {_get_spcs_token()}",
        "X-Snowflake-Authorization-Token-Type": "OAUTH",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }


def create_agent_thread():
    """POST /api/v2/cortex/threads. Returns thread_id int or None."""
    import requests as _req
    host = _get_snowflake_host()
    url = f"https://{host}{THREAD_CREATE_PATH}"
    try:
        r = _req.post(url, headers=_rest_headers(),
                      json={"origin_application": "RiskLensApp"}, timeout=30)
        if r.status_code in (200, 201):
            d = r.json()
            tid = d.get("thread_id") or d.get("id")
            if tid is not None:
                logger.info("Created Cortex thread %s", tid)
                return int(tid)
        logger.warning("Thread creation HTTP %s: %s", r.status_code, r.text[:300])
    except Exception as exc:
        logger.warning("Thread creation exception: %s", exc)
    return None


def _iter_sse(question, thread_id, parent_message_id):
    """Generator: yields parsed SSE event dicts from the Agent REST API."""
    import requests as _req
    host = _get_snowflake_host()
    url = f"https://{host}{AGENT_REST_PATH}"

    body = {
        "stream": True,
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
    }
    if thread_id is not None:
        body["thread_id"] = thread_id
        body["parent_message_id"] = parent_message_id if parent_message_id else 0

    try:
        resp = _req.post(url, headers=_rest_headers(), json=body,
                         stream=True, timeout=300)

        if resp.status_code in (401, 403):
            yield {"type": "error", "code": f"HTTP_{resp.status_code}",
                   "message": f"REST auth/permission failure ({resp.status_code})"}
            return
        if resp.status_code != 200:
            yield {"type": "error", "code": f"HTTP_{resp.status_code}",
                   "message": f"Agent endpoint returned {resp.status_code}"}
            return

        event_type = None
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8")

            if line.startswith("event:"):
                event_type = line[6:].strip()
                continue

            if line.startswith("data:"):
                data_str = line[5:].strip()
                if not event_type or not data_str:
                    event_type = None
                    continue
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    payload = {"raw": data_str}

                if event_type == "response.text.delta":
                    yield {"type": "delta", "text": payload.get("text", "")}
                elif event_type == "response.status":
                    yield {"type": "status",
                           "message": payload.get("message", ""),
                           "status": payload.get("status", "")}
                elif event_type == "response":
                    yield {"type": "response", "data": payload}
                elif event_type == "metadata":
                    yield {"type": "metadata", "data": payload.get("metadata", payload)}
                elif event_type == "response.warning":
                    yield {"type": "warning", "data": payload}
                elif event_type == "error":
                    yield {"type": "error",
                           "code": payload.get("code", ""),
                           "message": payload.get("message", str(payload))}
                elif event_type in ("response.tool_use", "response.tool_result"):
                    yield {"type": "tool_event", "event": event_type, "data": payload}
                event_type = None
                continue

            if line == "":
                event_type = None

    except Exception as exc:
        import requests as _req2
        if isinstance(exc, _req2.exceptions.Timeout):
            yield {"type": "error", "code": "TIMEOUT", "message": "REST timeout (300s)"}
        elif isinstance(exc, _req2.exceptions.ConnectionError):
            yield {"type": "error", "code": "CONNECTION", "message": str(exc)}
        else:
            yield {"type": "error", "code": "UNKNOWN", "message": str(exc)}


_STATUS_LABELS = {
    "planning": "Planning investigation...",
    "reasoning_agent_stop": "Reviewing results...",
    "proceeding_to_answer": "Synthesizing evidence...",
}
_TOOL_LABELS = {
    "AccountInvestigation": "Querying account data...",
    "TransactionInvestigation": "Querying transaction data...",
    "NetworkInvestigation": "Querying network data...",
    "InvestigationKnowledge": "Searching knowledge base...",
}


def run_rest_streaming(question, thread_id, parent_message_id, text_placeholder):
    """
    Drive the SSE stream, write deltas into *text_placeholder*.
    Returns (final_text, assistant_message_id, warnings, error_dict_or_None).
    """
    text = ""
    asst_msg_id = None
    warnings = []
    error = None
    status_el = st.empty()

    for ev in _iter_sse(question, thread_id, parent_message_id):
        t = ev["type"]
        if t == "delta":
            text += ev.get("text", "")
            text_placeholder.markdown(text + "▌")
        elif t == "status":
            label = _STATUS_LABELS.get(ev.get("status", ""), ev.get("message", ""))
            if label:
                status_el.caption(f"⏳ {label}")
        elif t == "metadata":
            md = ev.get("data", {})
            if md.get("role") == "assistant" and "message_id" in md:
                asst_msg_id = md["message_id"]
            if "assistant_message_id" in md:
                asst_msg_id = md["assistant_message_id"]
        elif t == "response":
            d = ev.get("data", {})
            if not text:
                for item in d.get("content", []):
                    if isinstance(item, dict) and item.get("type") == "text":
                        text += item.get("text", "")
            meta = d.get("metadata", {})
            if meta.get("assistant_message_id"):
                asst_msg_id = meta["assistant_message_id"]
            warnings.extend(d.get("warnings", []))
        elif t == "warning":
            warnings.append(ev.get("data", {}))
        elif t == "tool_event":
            name = ev.get("data", {}).get("name", "")
            if name and "tool_use" in ev.get("event", ""):
                status_el.caption(f"⏳ {_TOOL_LABELS.get(name, f'Using {name}...')}")
        elif t == "error":
            error = ev
            break

    status_el.empty()
    if text:
        text_placeholder.markdown(text)
    return text, asst_msg_id, warnings, error


# ===========================================================================
# LAYER B: DATA_AGENT_RUN (SQL, non-streaming)
# ===========================================================================

def call_agent_sql(question, thread_id=None, parent_message_id=None):
    """Returns (parsed_response_dict, error_dict_or_None)."""
    body = {"messages": [{"role": "user",
                          "content": [{"type": "text", "text": question}]}]}
    if thread_id is not None:
        body["thread_id"] = thread_id
        body["parent_message_id"] = parent_message_id if parent_message_id else 0
    payload = json.dumps(body)
    create_flag = "TRUE" if thread_id is None else "FALSE"

    sql = f"""
        SELECT TRY_PARSE_JSON(
            SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                '{AGENT_FQN}', $${payload}$$, {create_flag}
            )
        ) AS resp
    """
    try:
        df = run_query(sql)
        raw = df.iloc[0]["RESP"]
        if raw is None:
            return None, {"code": "EMPTY", "message": "DATA_AGENT_RUN returned NULL"}
        resp = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(resp, dict) and "code" in resp:
            code = str(resp["code"])
            if code == "391920":
                return None, {"code": "391920",
                              "message": resp.get("message", "Analyst execution-environment error")}
            if code.startswith("3") or code.startswith("4"):
                return None, {"code": code, "message": resp.get("message", "Agent error")}
        return resp, None
    except Exception as exc:
        return None, {"code": "SQL_ERROR", "message": str(exc)}


def extract_sql_response(resp):
    """Parse DATA_AGENT_RUN response → (text, asst_msg_id, thread_id, warnings)."""
    if not isinstance(resp, dict):
        return str(resp), None, None, []
    parts = []
    for item in resp.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item["text"])
    meta = resp.get("metadata", {})
    return (
        "\n\n".join(parts) if parts else json.dumps(resp, indent=2),
        meta.get("assistant_message_id"),
        meta.get("thread_id"),
        resp.get("warnings", []),
    )


# ===========================================================================
# LAYER C: Fallback Investigation Engine
# ===========================================================================
SEARCH_SVC = "RISKLENS.KNOWLEDGE.INVESTIGATION_SEARCH"
LLM_MODEL = "llama3.1-70b"


def classify_question(question):
    q = question.lower()
    acc = re.search(r'acc-\d{6}', q)
    aid = acc.group(0).upper() if acc else None
    if any(k in q for k in ["what is", "explain", "define", "how to", "guidance",
                              "methodology", "typology", "indicator", "escalat",
                              "false positive", "legitimate", "regulation",
                              "compliance", "sar", "bsa", "aml", "kyc",
                              "policy", "procedure"]):
        return "knowledge", aid
    if any(k in q for k in ["network", "connection", "link", "graph",
                              "beneficiar", "cycle", "chain", "shared device",
                              "relationship"]):
        return "network", aid
    if any(k in q for k in ["transaction", "txn", "payment", "transfer",
                              "amount", "cash", "threshold", "near-threshold",
                              "structur"]):
        return "transaction", aid
    if aid:
        return "account", aid
    if any(k in q for k in ["high risk", "risk tier", "overview", "summary",
                              "how many", "top", "worst", "flagged", "alert",
                              "portfolio", "distribution", "dashboard"]):
        return "account", aid
    return "knowledge", aid


def _search(query, limit=3):
    p = json.dumps({"query": query, "columns": ["TITLE", "CATEGORY", "CONTENT"], "limit": limit})
    try:
        df = run_query(f"SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW('{SEARCH_SVC}', $${p}$$))['results'] AS r")
        raw = df.iloc[0]["R"]
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []


def _fb_account(aid=None):
    if aid:
        return run_query("SELECT * FROM RISKLENS.ANALYTICS.INVESTIGATION_SUMMARY WHERE ACCOUNT_ID = :1", params=[aid])
    return run_query("""
        SELECT ACCOUNT_ID, CUSTOMER_ID, ACCOUNT_TYPE, CUSTOMER_SEGMENT,
               OBSERVABLE_RISK_TIER, TOTAL_INDICATOR_COUNT,
               STRUCTURING_INDICATOR_COUNT, CROSS_BORDER_INDICATOR_COUNT,
               ANOMALY_INDICATOR_COUNT, DORMANCY_INDICATOR_COUNT,
               NETWORK_INDICATOR_COUNT, TOTAL_TXN_COUNT, TOTAL_TXN_AMOUNT
        FROM RISKLENS.ANALYTICS.INVESTIGATION_SUMMARY
        WHERE OBSERVABLE_RISK_TIER IN ('HIGH','MEDIUM')
        ORDER BY TOTAL_INDICATOR_COUNT DESC LIMIT 20""")


def _fb_txn(aid=None):
    if aid:
        return run_query("""
            SELECT TRANSACTION_ID, ACCOUNT_ID, TRANSACTION_DATE, TRANSACTION_TYPE,
                   CHANNEL, AMOUNT, CURRENCY, COUNTERPARTY_COUNTRY,
                   NEAR_THRESHOLD_FLAG, IS_RAPID_SUCCESSION, IS_HIGH_RISK_COUNTRY,
                   IS_AMOUNT_OUTLIER, AMOUNT_Z_SCORE_RETROSPECTIVE
            FROM RISKLENS.ANALYTICS.TRANSACTION_RISK_FEATURES
            WHERE ACCOUNT_ID = :1 ORDER BY TRANSACTION_DATE DESC LIMIT 50""", params=[aid])
    return run_query("""
        SELECT TRANSACTION_ID, ACCOUNT_ID, TRANSACTION_DATE, TRANSACTION_TYPE,
               AMOUNT, NEAR_THRESHOLD_FLAG, IS_RAPID_SUCCESSION,
               IS_HIGH_RISK_COUNTRY, IS_AMOUNT_OUTLIER, AMOUNT_Z_SCORE_RETROSPECTIVE
        FROM RISKLENS.ANALYTICS.TRANSACTION_RISK_FEATURES
        WHERE NEAR_THRESHOLD_FLAG = TRUE OR IS_RAPID_SUCCESSION = TRUE
              OR IS_HIGH_RISK_COUNTRY = TRUE OR IS_AMOUNT_OUTLIER = TRUE
        ORDER BY TRANSACTION_DATE DESC LIMIT 30""")


def _fb_net(aid=None):
    if aid:
        return run_query("""
            SELECT ACCOUNT_A, ACCOUNT_B, LINK_TYPE, SHARED_RESOURCE, LINK_COUNT,
                   IS_RECIPROCAL, INVOLVES_TRIANGLE_MEMBER
            FROM RISKLENS.ANALYTICS.ACCOUNT_NETWORK_GRAPH
            WHERE ACCOUNT_A = :1 OR ACCOUNT_B = :1
            ORDER BY LINK_COUNT DESC LIMIT 30""", params=[aid])
    return run_query("""
        SELECT ACCOUNT_A, ACCOUNT_B, LINK_TYPE, SHARED_RESOURCE, LINK_COUNT
        FROM RISKLENS.ANALYTICS.ACCOUNT_NETWORK_GRAPH
        WHERE LINK_TYPE IN ('INTERNAL_BENEFICIARY','SHARED_DEVICE')
        ORDER BY LINK_COUNT DESC LIMIT 30""")


def _llm(question, context, data_summary=""):
    sys = ("You are the RiskLens Investigation Copilot, an expert AML/fraud analyst assistant. "
           "OBSERVABLE_RISK_TIER is a heuristic prioritization signal, NOT ground truth. "
           "Present findings as evidence requiring human judgment. Be concise, use bullets.")
    usr = f"Question: {question}\n\n"
    if context:
        usr += f"Knowledge Context:\n{context}\n\n"
    if data_summary:
        usr += f"Data Evidence:\n{data_summary}\n\n"
    usr += "Provide a clear, evidence-based response."
    prompt = json.dumps([{"role": "system", "content": sys}, {"role": "user", "content": usr}])
    try:
        df = run_query(f"""SELECT SNOWFLAKE.CORTEX.COMPLETE('{LLM_MODEL}',
            PARSE_JSON($${prompt}$$),
            OBJECT_CONSTRUCT('max_tokens',2000,'temperature',0.2)) AS r""")
        raw = df.iloc[0]["R"]
        resp = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(resp, dict):
            ch = resp.get("choices", [])
            if ch:
                c = ch[0]
                if isinstance(c.get("messages"), str):
                    return c["messages"]
                if isinstance(c.get("message"), dict):
                    return c["message"].get("content", str(resp))
                if isinstance(c.get("message"), str):
                    return c["message"]
            if "message" in resp:
                return resp["message"]
        return str(resp)
    except Exception as e:
        return f"Unable to generate summary: {e}"


def run_fallback(question):
    cat, aid = classify_question(question)
    sr = _search(question)
    ctx = "\n\n".join(f"[{r.get('TITLE','')}]: {r.get('CONTENT','')[:800]}" for r in sr[:2]) if sr else ""
    data_df = {"account": _fb_account, "transaction": _fb_txn, "network": _fb_net}.get(cat, lambda a: None)(aid)
    ds = ""
    if data_df is not None and not data_df.empty:
        ds = data_df.head(5).to_string(index=False) if len(data_df) > 5 else data_df.to_string(index=False)
        if len(data_df) > 5:
            ds = f"{len(data_df)} rows. Top 5:\n{ds}"
    return _llm(question, ctx, ds), data_df, sr


# ===========================================================================
# Cached overview
# ===========================================================================
@st.cache_data(ttl=300)
def get_risk_overview():
    return run_query("""
        SELECT COUNT(*) AS total_accounts,
            SUM(CASE WHEN OBSERVABLE_RISK_TIER='HIGH' THEN 1 ELSE 0 END) AS high_risk,
            SUM(CASE WHEN OBSERVABLE_RISK_TIER='MEDIUM' THEN 1 ELSE 0 END) AS medium_risk,
            SUM(CASE WHEN OBSERVABLE_RISK_TIER='LOW' THEN 1 ELSE 0 END) AS low_risk
        FROM RISKLENS.ANALYTICS.INVESTIGATION_SUMMARY""").iloc[0]


@st.cache_data(ttl=300)
def get_high_risk_accounts():
    return run_query("""
        SELECT ACCOUNT_ID, CUSTOMER_SEGMENT, OBSERVABLE_RISK_TIER,
               TOTAL_INDICATOR_COUNT, STRUCTURING_INDICATOR_COUNT,
               CROSS_BORDER_INDICATOR_COUNT, NETWORK_INDICATOR_COUNT,
               TOTAL_TXN_AMOUNT
        FROM RISKLENS.ANALYTICS.INVESTIGATION_SUMMARY
        WHERE OBSERVABLE_RISK_TIER='HIGH'
        ORDER BY TOTAL_INDICATOR_COUNT DESC LIMIT 10""")


# ===========================================================================
# Session state
# ===========================================================================
_DEFAULTS = {
    "messages": [],
    "pending_prompt": None,
    "execution_mode": None,
    "agent_thread_id": None,
    "agent_parent_message_id": None,
    "rest_probed": False,
    "rest_available": False,
    "sql_agent_failed": False,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

MODE_LABELS = {
    "rest": ("Cortex Agent (REST Streaming)", "exec-rest"),
    "sql": ("Cortex Agent (SQL)", "exec-sql"),
    "fallback": ("Fallback Investigation Engine", "exec-fallback"),
}


def _badge(mode=None):
    m = mode or st.session_state.execution_mode
    if m and m in MODE_LABELS:
        lbl, cls = MODE_LABELS[m]
        st.markdown(f'<span class="exec-mode {cls}">Execution: {lbl}</span>', unsafe_allow_html=True)


def _msg_label(mode):
    if mode and mode in MODE_LABELS:
        st.caption(f"*{MODE_LABELS[mode][0]}*")


# ===========================================================================
# Probe REST availability (once)
# ===========================================================================
if not st.session_state.rest_probed:
    st.session_state.rest_available = rest_api_available()
    st.session_state.rest_probed = True
    logger.info("REST available: %s", st.session_state.rest_available)


# ===========================================================================
# Sidebar
# ===========================================================================
with st.sidebar:
    st.markdown('<div class="main-header">RiskLens</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Investigation Copilot</div>', unsafe_allow_html=True)

    m = st.session_state.execution_mode
    if m == "rest":
        st.markdown("**Status:** <span class='status-ok'>Agent Online (REST)</span>", unsafe_allow_html=True)
    elif m == "sql":
        st.markdown("**Status:** <span class='status-ok'>Agent Online (SQL)</span>", unsafe_allow_html=True)
    elif m == "fallback":
        st.markdown("**Status:** <span class='status-warn'>Fallback Mode</span>", unsafe_allow_html=True)
    else:
        st.markdown("**Status:** Ready", unsafe_allow_html=True)

    st.divider()
    st.markdown("### Portfolio Overview")
    try:
        ov = get_risk_overview()
        c1, c2 = st.columns(2)
        c1.metric("HIGH Risk", int(ov["HIGH_RISK"]))
        c2.metric("MEDIUM Risk", int(ov["MEDIUM_RISK"]))
        c3, c4 = st.columns(2)
        c3.metric("LOW Risk", int(ov["LOW_RISK"]))
        c4.metric("Total Accounts", int(ov["TOTAL_ACCOUNTS"]))
    except Exception:
        st.caption("Unable to load overview.")

    st.divider()
    st.markdown("### Quick Investigations")
    for label, prompt in [
        ("High-Risk Overview", "Show me all HIGH risk accounts with their indicator breakdown."),
        ("Structuring Alerts", "Which accounts show the strongest structuring indicators?"),
        ("Cross-Border Activity", "Summarize accounts with cross-border risk indicators."),
        ("Network Anomalies", "Which accounts have suspicious network connections or shared devices?"),
        ("Dormant Activations", "Show accounts with dormancy reactivation patterns."),
        ("Investigation Guide", "What is the recommended methodology for investigating a flagged account?"),
    ]:
        if st.button(label, key=f"qp_{label}", use_container_width=True):
            st.session_state.pending_prompt = prompt

    st.divider()
    st.markdown("### Account Lookup")
    _ai = st.text_input("Account ID", placeholder="ACC-000061", key="acct_lookup")
    if st.button("Investigate", key="btn_inv", use_container_width=True) and _ai:
        aid = _ai.strip().upper()
        if not aid.startswith("ACC-"):
            aid = f"ACC-{aid.zfill(6)}"
        st.session_state.pending_prompt = f"Provide a comprehensive investigation summary for account {aid}."

    st.divider()
    if st.button("Clear Conversation", use_container_width=True):
        for k, v in _DEFAULTS.items():
            st.session_state[k] = v
        st.rerun()
    st.caption("RiskLens v2.0 | Synthetic Data Only")
    st.caption("OBSERVABLE_RISK_TIER is a heuristic signal, not ground truth.")


# ===========================================================================
# Main header
# ===========================================================================
st.markdown('<div class="main-header">RiskLens Investigation Copilot</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Banking Risk, Fraud & Regulatory Intelligence | Powered by Snowflake Cortex</div>', unsafe_allow_html=True)
_badge()

if not st.session_state.messages:
    st.markdown("""
**Welcome to RiskLens.** Ask questions about accounts, transactions, network relationships,
or AML investigation methodology.

**Example questions:**
- *"Investigate account ACC-000061 for structuring activity"*
- *"Which accounts have the highest total indicator counts?"*
- *"What are the key steps in an AML investigation?"*
- *"Show network connections for ACC-000012"*
""")
    with st.expander("Top HIGH-Risk Accounts", expanded=True):
        try:
            st.dataframe(get_high_risk_accounts(), use_container_width=True, hide_index=True,
                         column_config={"TOTAL_TXN_AMOUNT": st.column_config.NumberColumn("Txn Volume", format="$%.2f")})
        except Exception as e:
            st.error(str(e))


# ===========================================================================
# Render chat history
# ===========================================================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("exec_mode"):
            _msg_label(msg["exec_mode"])
        if msg.get("exec_note"):
            st.warning(msg["exec_note"])
        if msg.get("evidence_df") is not None:
            with st.expander("Evidence Data", expanded=False):
                st.dataframe(msg["evidence_df"], use_container_width=True, hide_index=True)
        if msg.get("search_results"):
            with st.expander("Knowledge Sources", expanded=False):
                for r in msg["search_results"]:
                    st.markdown(f"**{r.get('TITLE','')}** ({r.get('CATEGORY','')})")
                    st.caption(r.get("CONTENT", "")[:400] + ("..." if len(r.get("CONTENT", "")) > 400 else ""))
                    st.divider()


# ===========================================================================
# Fallback display helper
# ===========================================================================
def _show_fallback(question):
    """Run fallback engine, display result, return message dict."""
    with st.spinner("Using fallback investigation engine..."):
        text, df, sr = run_fallback(question)
    st.markdown(text)
    st.warning("Agent temporarily unavailable — using fallback investigation engine.")
    _msg_label("fallback")
    if df is not None and not df.empty:
        with st.expander("Evidence Data", expanded=True):
            st.dataframe(df, use_container_width=True, hide_index=True)
    if sr:
        with st.expander("Knowledge Sources", expanded=False):
            for r in sr:
                st.markdown(f"**{r.get('TITLE','')}** ({r.get('CATEGORY','')})")
                st.caption(r.get("CONTENT","")[:400] + ("..." if len(r.get("CONTENT",""))>400 else ""))
                st.divider()
    m = {"role": "assistant", "content": text, "exec_mode": "fallback",
         "exec_note": "Agent temporarily unavailable — using fallback investigation engine."}
    if df is not None and not df.empty:
        m["evidence_df"] = df
    if sr:
        m["search_results"] = sr
    st.session_state.execution_mode = "fallback"
    return m


# ===========================================================================
# Main question handler
# ===========================================================================
def handle_question(question):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        # --- Layer A: REST Streaming ---
        if st.session_state.rest_available:
            # Ensure thread
            if st.session_state.agent_thread_id is None:
                tid = create_agent_thread()
                if tid is not None:
                    st.session_state.agent_thread_id = tid
                    st.session_state.agent_parent_message_id = 0
                else:
                    logger.warning("Thread creation failed; disabling REST path")
                    st.session_state.rest_available = False

            if st.session_state.rest_available and st.session_state.agent_thread_id is not None:
                ph = st.empty()
                text, asst_id, warnings, err = run_rest_streaming(
                    question,
                    st.session_state.agent_thread_id,
                    st.session_state.agent_parent_message_id or 0,
                    ph,
                )
                if text and not err:
                    if asst_id is not None:
                        st.session_state.agent_parent_message_id = asst_id
                    st.session_state.execution_mode = "rest"
                    _msg_label("rest")
                    st.session_state.messages.append({
                        "role": "assistant", "content": text, "exec_mode": "rest"})
                    return
                # REST failed — clear placeholder and continue
                ph.empty()
                if err:
                    logger.warning("REST error: %s", err)
                    code = err.get("code", "")
                    if code in ("HTTP_401", "HTTP_403", "CONNECTION", "AUTH_FAILURE", "PERMISSION_FAILURE"):
                        st.session_state.rest_available = False

        # --- Layer B: DATA_AGENT_RUN SQL ---
        if not st.session_state.sql_agent_failed:
            with st.spinner("Querying Cortex Agent (SQL)..."):
                resp, err = call_agent_sql(
                    question,
                    thread_id=st.session_state.agent_thread_id,
                    parent_message_id=st.session_state.agent_parent_message_id,
                )
            if resp and not err:
                text, asst_id, tid, warnings = extract_sql_response(resp)
                if text and text.strip():
                    if asst_id is not None:
                        st.session_state.agent_parent_message_id = asst_id
                    if tid is not None and st.session_state.agent_thread_id is None:
                        st.session_state.agent_thread_id = tid
                    st.session_state.execution_mode = "sql"
                    st.markdown(text)
                    _msg_label("sql")
                    st.session_state.messages.append({
                        "role": "assistant", "content": text, "exec_mode": "sql"})
                    return
            if err:
                logger.warning("SQL agent error: %s", err)

        # --- Layer C: Fallback ---
        m = _show_fallback(question)
        st.session_state.messages.append(m)


# ===========================================================================
# Route input
# ===========================================================================
active_question = None
if st.session_state.pending_prompt:
    active_question = st.session_state.pending_prompt
    st.session_state.pending_prompt = None

user_input = st.chat_input("Ask about accounts, transactions, networks, or investigation methodology...")
if user_input and active_question is None:
    active_question = user_input

if active_question:
    handle_question(active_question)
