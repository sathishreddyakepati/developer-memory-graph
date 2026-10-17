import os
import streamlit as st
from memory import save_memory
from retrieval import search_memories, get_graph_data, get_graph_stats
from db import get_connection_params
from agent import (
    AgentResponse,
    ask_developer_memory_agent,
    get_configured_model,
    get_bounded_timeout,
    sanitize_error_message,
)
from streamlit_agraph import agraph, Node, Edge, Config

st.set_page_config(
    page_title="Developer Memory Graph · AI Agent Workspace",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# High-contrast, dense, polished dark developer workspace
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap');

    /* Design System Tokens (Linear & Sentry Workbench) */
    :root {
        --bg-canvas: #090d16;
        --bg-surface: #0f1422;
        --bg-surface-elevated: #151b2d;
        --bg-surface-subtle: #111728;
        --border-subtle: #1b2339;
        --border-muted: #242f4c;
        --border-focus: #4f5df5;
        --text-primary: #f1f5f9;
        --text-secondary: #94a3b8;
        --text-muted: #64748b;
        --accent-indigo: #4f5df5;
        --accent-indigo-hover: #4351e8;
        --status-green: #10b981;
        --status-green-subtle: rgba(16, 185, 129, 0.12);
        --status-red: #f43f5e;
        --status-red-subtle: rgba(244, 63, 94, 0.1);
        --status-amber: #f59e0b;
        --font-mono: 'JetBrains Mono', SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Core Canvas */
    .stApp {
        background-color: var(--bg-canvas) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-sans) !important;
    }

    /* Fix Streamlit Header & Toolbar overlap */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 2.5rem !important;
    }

    /* Minimal Viewport Padding with safe top clearance */
    .block-container {
        padding-top: 3.25rem !important;
        padding-bottom: 2rem !important;
        max-width: 98% !important;
    }

    /* Workbench Header */
    .workbench-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.85rem 1.15rem;
        margin-bottom: 1.25rem;
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 6px;
    }
    .workbench-header-left {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    .workbench-title-row {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .workbench-title {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        color: var(--text-primary) !important;
        letter-spacing: -0.02em;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2;
    }
    .workbench-subtitle {
        font-size: 0.78rem;
        color: var(--text-secondary);
        margin: 0;
    }
    .workbench-tag {
        font-size: 0.68rem;
        font-weight: 500;
        font-family: var(--font-mono);
        letter-spacing: 0.03em;
        padding: 2px 8px;
        border-radius: 4px;
        background: var(--bg-surface-elevated);
        color: var(--text-secondary);
        border: 1px solid var(--border-muted);
    }

    /* Linear-Style Minimal Sidebar */
    [data-testid="stSidebar"] {
        background-color: var(--bg-surface) !important;
        border-right: 1px solid var(--border-subtle) !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        font-size: 0.84rem !important;
        color: var(--text-secondary) !important;
        padding: 4px 6px !important;
        border-radius: 4px !important;
        transition: background 0.12s ease !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background: var(--bg-surface-elevated) !important;
        color: var(--text-primary) !important;
    }
    .sidebar-workbench-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 2px 0 10px 0;
        border-bottom: 1px solid var(--border-subtle);
        margin-bottom: 12px;
    }
    .sidebar-workbench-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--text-primary);
        letter-spacing: -0.01em;
    }
    .sidebar-workbench-sub {
        font-size: 0.7rem;
        color: var(--text-muted);
    }

    /* Telemetry Group Card */
    .telemetry-group {
        background: var(--bg-surface-subtle);
        border: 1px solid var(--border-subtle);
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 10px;
    }
    .telemetry-group-header {
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-muted);
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .telemetry-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.76rem;
        padding: 2px 0;
        color: var(--text-secondary);
    }
    .telemetry-mono-tag {
        font-family: var(--font-mono);
        font-size: 0.7rem;
        color: var(--text-primary);
        background: var(--bg-surface);
        padding: 1px 5px;
        border-radius: 3px;
        border: 1px solid var(--border-subtle);
    }
    .status-dot-active {
        display: inline-block;
        width: 6px;
        height: 6px;
        background-color: var(--status-green);
        border-radius: 50%;
        margin-right: 5px;
    }

    /* Raycast / Sentry Diagnostic Banner */
    .diagnostic-strip {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
    }
    .diagnostic-phase {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.78rem;
    }
    .diagnostic-label {
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-muted);
    }
    .diagnostic-value {
        color: var(--text-primary);
        font-weight: 500;
    }

    /* Section Headings */
    .section-label {
        font-size: 0.88rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .section-sublabel {
        font-size: 0.74rem;
        color: var(--text-muted);
        margin-bottom: 8px;
    }

    /* Sentry Technical Evidence Card */
    .evidence-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-left: 3px solid var(--border-muted);
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 10px;
    }
    .evidence-card-verified {
        border-left-color: var(--status-green) !important;
    }
    .evidence-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }
    .evidence-card-title {
        font-size: 0.88rem;
        font-weight: 600;
        color: var(--text-primary);
    }
    .pill-verified {
        font-family: var(--font-mono);
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 1px 6px;
        border-radius: 3px;
        background: var(--status-green-subtle);
        color: var(--status-green);
        border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .pill-recorded {
        font-family: var(--font-mono);
        font-size: 0.65rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 1px 6px;
        border-radius: 3px;
        background: var(--bg-surface-elevated);
        color: var(--text-muted);
        border: 1px solid var(--border-subtle);
    }
    .pill-ai-proposed {
        font-family: var(--font-mono);
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 2px 8px;
        border-radius: 4px;
        background: rgba(99, 102, 241, 0.1);
        color: #818cf8;
        border: 1px solid rgba(99, 102, 241, 0.25);
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 10px;
    }

    /* Stack Trace / Graph Traversal Breadcrumb */
    .traversal-path {
        background: var(--bg-canvas);
        border: 1px solid var(--border-subtle);
        border-radius: 4px;
        padding: 5px 8px;
        margin: 6px 0;
        font-family: var(--font-mono);
        font-size: 0.72rem;
        color: var(--text-muted);
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 4px;
    }
    .traversal-step-session {
        color: #38bdf8;
    }
    .traversal-arrow {
        color: var(--text-muted);
        font-size: 0.68rem;
    }
    .traversal-step-error {
        color: var(--status-red);
    }
    .traversal-step-solution {
        color: var(--status-green);
    }

    .evidence-block-error {
        font-family: var(--font-mono);
        font-size: 0.75rem;
        color: #fca5a5;
        background: var(--bg-canvas);
        border: 1px solid var(--border-subtle);
        border-radius: 4px;
        padding: 6px 8px;
        margin: 6px 0;
        word-break: break-word;
    }
    .evidence-block-sol {
        font-size: 0.8rem;
        color: var(--text-secondary);
        background: var(--bg-surface-subtle);
        border: 1px solid var(--border-subtle);
        border-radius: 4px;
        padding: 6px 8px;
        margin-top: 6px;
        white-space: pre-wrap;
        line-height: 1.4;
    }
    .evidence-card-meta {
        font-size: 0.7rem;
        color: var(--text-muted);
        margin-top: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    /* Sentry Technical Empty State Box */
    .workbench-empty-box {
        background: var(--bg-surface);
        border: 1px dashed var(--border-muted);
        border-radius: 6px;
        padding: 24px 16px;
        text-align: center;
        color: var(--text-muted);
        margin-top: 4px;
    }
    .workbench-empty-box h4 {
        color: var(--text-primary);
        margin: 6px 0 4px 0;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .workbench-empty-box p {
        font-size: 0.78rem;
        margin: 0;
        color: var(--text-secondary);
    }

    /* Raycast Form Inputs */
    .stTextArea textarea {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.84rem !important;
        padding: 8px 10px !important;
        border-radius: 5px !important;
    }
    .stTextArea textarea:focus {
        border-color: var(--border-focus) !important;
        box-shadow: 0 0 0 1px var(--border-focus) !important;
    }

    .stTextInput input {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        color: var(--text-primary) !important;
        font-size: 0.84rem !important;
        border-radius: 5px !important;
    }
    .stTextInput input:focus {
        border-color: var(--border-focus) !important;
        box-shadow: 0 0 0 1px var(--border-focus) !important;
    }

    /* Primary Command Button (Raycast / Linear Restrained Style) */
    button[kind="primary"] {
        background: var(--accent-indigo) !important;
        color: #ffffff !important;
        border: 1px solid #6366f1 !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        padding: 0.45rem 1rem !important;
        border-radius: 5px !important;
        transition: background 0.15s ease !important;
        box-shadow: none !important;
    }
    button[kind="primary"]:hover {
        background: var(--accent-indigo-hover) !important;
        border-color: #818cf8 !important;
    }

    /* Secondary / Preset Buttons (Quiet Raycast Chips) */
    button[kind="secondary"] {
        background: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        color: var(--text-secondary) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.76rem !important;
        padding: 0.25rem 0.6rem !important;
        border-radius: 4px !important;
        transition: all 0.12s ease !important;
    }
    button[kind="secondary"]:hover {
        background: var(--bg-surface-elevated) !important;
        border-color: var(--border-muted) !important;
        color: var(--text-primary) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize persistent session state for agent execution
if "agent_loading" not in st.session_state:
    st.session_state["agent_loading"] = False
if "agent_response" not in st.session_state:
    st.session_state["agent_response"] = None
if "agent_last_query" not in st.session_state:
    st.session_state["agent_last_query"] = ""

# -------------------- SIDEBAR TELEMETRY & NAVIGATION --------------------

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-workbench-header">
            <div style="color:var(--accent-indigo); font-size:1.15rem; font-weight:700;">◆</div>
            <div>
                <div class="sidebar-workbench-title">Developer Memory</div>
                <div class="sidebar-workbench-sub">Graph-Grounded Debugging</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_mode = st.radio(
        "Workspace Navigation",
        [
            "🤖 AI Debugger Agent",
            "➕ Save a Memory",
            "🔍 Search Memories",
            "🕸️ Memory Graph",
        ],
        label_visibility="collapsed",
    )

    st.markdown('<div style="margin: 12px 0; border-top: 1px solid var(--border-subtle);"></div>', unsafe_allow_html=True)

    # FalkorDB Cluster Telemetry (Zero credentials or raw host/port exposed)
    conn_params = get_connection_params()
    falkor_tls = conn_params.get("ssl", False)

    # Live Graph Memory Statistics (Real runtime query)
    try:
        sessions, errors, solutions, relationships = get_graph_stats()
        stats_line = f"{sessions}S · {errors}E · {solutions}Sol · {relationships}R"
    except Exception as exc:
        sessions, errors, solutions, relationships = 0, 0, 0, 0
        stats_line = "Offline"

    model_name = get_configured_model()
    default_timeout = int(get_bounded_timeout())

    st.markdown(
        f"""
        <div class="telemetry-group">
            <div class="telemetry-group-header">
                <span>Infrastructure</span>
                <span><span class="status-dot-active"></span>Live</span>
            </div>
            <div class="telemetry-row">
                <span>Graph Cluster</span>
                <span class="telemetry-mono-tag">FalkorDB Cloud</span>
            </div>
            <div class="telemetry-row">
                <span>TLS Security</span>
                <span class="telemetry-mono-tag">{'Enabled' if falkor_tls else 'Disabled'}</span>
            </div>
            <div class="telemetry-row">
                <span>Target Graph</span>
                <span class="telemetry-mono-tag">developer_memory</span>
            </div>
            <div class="telemetry-row">
                <span>Memory Knowledge</span>
                <span class="telemetry-mono-tag">{stats_line}</span>
            </div>
        </div>

        <div class="telemetry-group">
            <div class="telemetry-group-header">
                <span>Inference Engine</span>
                <span class="telemetry-mono-tag">OpenRouter</span>
            </div>
            <div class="telemetry-row">
                <span>Active Model</span>
                <span class="telemetry-mono-tag">{model_name.split('/')[-1][:16]}</span>
            </div>
            <div class="telemetry-row">
                <span>Bounded Timeout</span>
                <span class="telemetry-mono-tag">{default_timeout}s</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption("FalkorDB Graph Hacks · Agent Memory Track")

# -------------------- MAIN WORKSPACE --------------------

# 1. AI DEBUGGER AGENT
if nav_mode == "🤖 AI Debugger Agent":
    st.markdown(
        """
        <div class="workbench-header">
            <div class="workbench-header-left">
                <div class="workbench-title-row">
                    <h1 class="workbench-title">Developer Memory Workbench</h1>
                    <span class="workbench-tag">FalkorDB × OpenRouter</span>
                </div>
                <div class="workbench-subtitle">
                    Grounded debugging intelligence retrieved from your team's persistent graph memory.
                </div>
            </div>
            <div class="workbench-tag" style="color:var(--accent-indigo); border-color:rgba(79, 93, 245, 0.3);">
                Agent Memory Track
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Preset Helper Chips (Raycast style quiet command chips)
    st.markdown('<div class="section-sublabel" style="margin-bottom:4px;">Quick example queries:</div>', unsafe_allow_html=True)
    p_col1, p_col2, p_col3 = st.columns(3)
    if p_col1.button("ensurepip venv error", use_container_width=True):
        st.session_state["agent_query_input"] = "ensurepip unavailable when creating venv"
    if p_col2.button("git push rejected", use_container_width=True):
        st.session_state["agent_query_input"] = "failed to push some refs to remote repository updates were rejected"
    if p_col3.button("kafka connection error", use_container_width=True):
        st.session_state["agent_query_input"] = "Kafka broker connection refused in Rust client on port 9092"

    st.markdown('<div style="margin-top:6px;"></div>', unsafe_allow_html=True)

    # Primary Query Input Text Area (FIRST text_area in DOM: critical for AppTest compatibility)
    query_input = st.text_area(
        "Your question or pasted traceback:",
        placeholder="Enter an error message, stack trace, or debugging question...",
        height=85,
        key="agent_query_input",
    )

    retry_triggered = st.session_state.pop("agent_retry_trigger", False)
    consult_btn = st.button("Consult Memory Agent", type="primary", use_container_width=True)

    # Agent Execution Pipeline Trigger
    if consult_btn or retry_triggered:
        if not query_input.strip():
            st.warning("Please enter a question or paste a traceback.")
        else:
            st.session_state["agent_loading"] = True
            st.session_state["agent_last_query"] = query_input.strip()
            try:
                with st.status("Agent Execution Pipeline Active...", expanded=True) as status_box:
                    status_box.write("Phase 1: Querying FalkorDB memory graph for historical team experiences...")
                    response = ask_developer_memory_agent(query_input.strip())
                    st.session_state["agent_response"] = response

                    status_box.write(f"Phase 2: Synthesizing recommendations via OpenRouter ({response.model_used or model_name})...")

                    if response.success:
                        status_box.update(label="Agent Execution Complete", state="complete", expanded=False)
                    elif response.is_timeout:
                        status_box.update(label="OpenRouter Inference Timed Out", state="error", expanded=True)
                    else:
                        status_box.update(label="Agent Request Failed", state="error", expanded=True)
            except Exception as exc:
                st.session_state["agent_response"] = AgentResponse(
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=sanitize_error_message(str(exc)),
                    retrieval_status="unknown",
                    inference_status="error",
                    inference_error=sanitize_error_message(str(exc)),
                )
            finally:
                st.session_state["agent_loading"] = False

    # Render Results from Session State
    response: AgentResponse | None = st.session_state.get("agent_response")

    if response is not None:
        # Diagnostic Strip (Linear/Raycast single line metrics)
        ret_time = f"{response.retrieval_time_seconds:.2f}s" if response.retrieval_time_seconds else "<0.01s"
        inf_time = f"{response.inference_time_seconds:.2f}s" if response.inference_time_seconds else "—"
        ev_count = len(response.evidence) if response.has_historical_evidence else 0

        ret_label = "Grounded" if response.has_historical_evidence else ("Query Error" if response.retrieval_status == "error" else "Zero-Shot")
        inf_label = "Succeeded" if response.success else ("Timed Out" if response.is_timeout else "Failed")

        st.markdown(
            f"""
            <div class="diagnostic-strip">
                <div class="diagnostic-phase">
                    <span class="diagnostic-label">Graph Retrieval:</span>
                    <span class="diagnostic-value">{ret_label}</span>
                    <span class="telemetry-mono-tag">{ev_count} records · {ret_time}</span>
                </div>
                <div class="diagnostic-phase">
                    <span class="diagnostic-label">Inference:</span>
                    <span class="diagnostic-value">{inf_label}</span>
                    <span class="telemetry-mono-tag">{response.model_used or model_name} · {inf_time}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Split Interface: Central AI Recommendations & Right Contextual Memory Panel
        col_main, col_panel = st.columns([7, 5])

        with col_main:
            st.markdown('<div class="section-label">Troubleshooting Recommendations</div>', unsafe_allow_html=True)

            # 1. Error / Timeout Handling
            if response.is_timeout or response.error_type == "timeout":
                timeout_display = int(response.timeout_seconds or default_timeout)
                timing_note = f" (elapsed: {response.inference_time_seconds:.1f}s)" if response.inference_time_seconds else ""
                st.error(
                    f"**OpenRouter Inference Timeout ({timeout_display}s{timing_note})**\n\n"
                    f"{response.error_message}\n\n"
                    "The upstream OpenRouter model queue took longer than the allotted timeout. "
                    "Notice on the right panel that your FalkorDB graph retrieval succeeded independently."
                )

                def _trigger_retry():
                    st.session_state["agent_retry_trigger"] = True

                c_ret1, c_ret2 = st.columns([1, 2])
                with c_ret1:
                    st.button(
                        "Retry OpenRouter Inference",
                        type="primary",
                        key="retry_agent_btn",
                        on_click=_trigger_retry,
                    )
                with c_ret2:
                    st.caption("Manual retry trigger. Automatic infinite loops are disabled.")

            elif not response.success:
                st.error(f"**Agent Request Failed:** {response.error_message}")
                if response.error_type == "auth_missing":
                    st.info("Tip: Configure `OPENROUTER_API_KEY` in your `.env` file to enable AI inference.")
                else:
                    def _trigger_generic_retry():
                        st.session_state["agent_retry_trigger"] = True

                    st.button("Retry Request", key="retry_generic_btn", on_click=_trigger_generic_retry)

            else:
                # Successfully Generated Grounded Advice
                st.markdown(
                    """
                    <div class="pill-ai-proposed">
                        <span>AI-Synthesized Advice · Unverified</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(response.answer)

                st.warning(
                    "Safety Notice: Review all code and shell commands carefully before executing. "
                    "Commands are never executed automatically by the agent."
                )

                # Human Verification Workflow (Save Verified Solution)
                st.markdown('<div style="margin: 12px 0; border-top: 1px solid var(--border-subtle);"></div>', unsafe_allow_html=True)
                st.markdown("**Did this solution resolve your issue?**")
                st.caption(
                    "Record this verified solution to your team's FalkorDB knowledge graph "
                    "so agents can reuse it in future debugging sessions:"
                )

                with st.expander("Save Verified Solution to Graph Memory", expanded=False):
                    with st.form("confirm_save_form", clear_on_submit=True):
                        active_query = st.session_state.get("agent_last_query", query_input)
                        first_line = active_query.strip().splitlines()[0][:50] if active_query.strip() else "Verified Solution"
                        save_title = st.text_input("Session Title", value=f"Fix: {first_line}")
                        save_error = st.text_area("Error / Challenge Pattern", value=active_query.strip()[:400])
                        save_solution = st.text_area(
                            "Working Solution Verified by You",
                            placeholder="Enter the exact commands or steps that resolved the problem...",
                        )
                        save_submit = st.form_submit_button("Confirm & Save Verified Solution", type="primary")

                    if save_submit:
                        if not all([save_title.strip(), save_error.strip(), save_solution.strip()]):
                            st.warning("Please complete all three fields to record the verified memory.")
                        else:
                            try:
                                saved_res = save_memory(
                                    save_title.strip(),
                                    save_error.strip(),
                                    save_solution.strip(),
                                    status="verified",
                                )
                                st.success(f"Verified memory saved! Memory ID: `{saved_res['memory_id']}`")
                                st.info("The graph memory and statistics will reflect this on next rerun.")
                            except Exception as save_err:
                                st.error(f"Could not save memory: {sanitize_error_message(str(save_err))}")

        with col_panel:
            st.markdown('<div class="section-label">Contextual FalkorDB Evidence</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-sublabel">Historical team sessions & verified solutions from FalkorDB graph.</div>', unsafe_allow_html=True)

            # Independent FalkorDB Retrieval Diagnostics (Strict string matching for regression tests)
            if response.retrieval_status == "error":
                st.warning(f"FalkorDB Retrieval Diagnostic: Graph query encountered an error: {response.retrieval_error}")
            elif response.has_historical_evidence:
                timing_note = f" in {response.retrieval_time_seconds:.2f}s" if response.retrieval_time_seconds else ""
                st.success(
                    f"FalkorDB Retrieval Diagnostic: Grounded in {len(response.evidence)} Historical Team Memory Record(s) from FalkorDB{timing_note}"
                )

                for idx, ev in enumerate(response.evidence, start=1):
                    created_display = ev.get('created_at', 'Recorded')
                    matched_badge = f"Matched: '{ev['matched_term']}'" if ev.get('matched_term') else ""
                    relevance_pts = f"{ev.get('relevance', 1)} pts"
                    ev_status = ev.get("status", "recorded").lower()

                    if ev_status == "verified":
                        status_html = '<span class="pill-verified">Verified</span>'
                        card_class = "evidence-card evidence-card-verified"
                    else:
                        status_html = '<span class="pill-recorded">Recorded</span>'
                        card_class = "evidence-card"

                    # Safely truncate node preview labels for breadcrumbs
                    s_label = ev['session'][:30] + "..." if len(ev['session']) > 30 else ev['session']
                    e_label = ev['error'][:30] + "..." if len(ev['error']) > 30 else ev['error']
                    sol_label = ev['solution'][:30] + "..." if len(ev['solution']) > 30 else ev['solution']

                    st.markdown(
                        f"""
                        <div class="{card_class}">
                            <div class="evidence-card-header">
                                <span class="evidence-card-title">{idx}. {ev['session']}</span>
                                {status_html}
                            </div>
                            <div class="traversal-path" title="FalkorDB Cypher path traversed">
                                <span class="traversal-step-session">Session: {s_label}</span>
                                <span class="traversal-arrow">─[:ENCOUNTERED]─▶</span>
                                <span class="traversal-step-error">Error: {e_label}</span>
                                <span class="traversal-arrow">─[:RESOLVED_BY]─▶</span>
                                <span class="traversal-step-solution">Solution: {sol_label}</span>
                            </div>
                            <div class="evidence-block-error">{ev['error']}</div>
                            <div class="evidence-block-sol"><strong>Solution:</strong> {ev['solution']}</div>
                            <div class="evidence-card-meta">
                                <span>Logged: {created_display}</span>
                                <span>Cypher Relevance: {relevance_pts}{f" · {matched_badge}" if matched_badge else ""}</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            elif response.retrieval_status == "no_matches" or (response.retrieval_status == "success" and not response.has_historical_evidence):
                st.info(
                    "FalkorDB Retrieval Diagnostic: No matching historical records found in your FalkorDB memory graph for this specific issue."
                )
                st.markdown(
                    """
                    <div class="workbench-empty-box">
                        <h4>Zero-Shot Inference Mode</h4>
                        <p>No previous team memories matched this error pattern in FalkorDB.<br>
                        The agent relied on general LLM reasoning. When a solution works, verify and save it to expand team memory.</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    else:
        # Initial Workspace Empty State
        col_main, col_panel = st.columns([7, 5])
        with col_main:
            st.markdown(
                """
                <div class="workbench-empty-box">
                    <h4>Ready to Debug</h4>
                    <p>Enter an error message, stack trace, or debugging question above.<br>
                    You can also click one of the quick presets to test real graph retrieval & LLM synthesis.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_panel:
            st.markdown('<div class="section-label">Contextual FalkorDB Evidence</div>', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="workbench-empty-box">
                    <h4>Awaiting Query</h4>
                    <p>Historical sessions, error patterns, and verified solutions from your FalkorDB knowledge graph will appear here.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

# 2. SAVE MEMORY WORKFLOW
elif nav_mode == "➕ Save a Memory":
    st.markdown(
        """
        <div class="workbench-header">
            <div class="workbench-header-left">
                <div class="workbench-title-row">
                    <h1 class="workbench-title">Capture Development Memory</h1>
                    <span class="workbench-tag">FalkorDB Graph Storage</span>
                </div>
                <div class="workbench-subtitle">
                    Record a debugging session, error pattern, and working solution to your team's knowledge graph.
                </div>
            </div>
            <div class="workbench-tag">Persistent Memory</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("save_memory_form", clear_on_submit=True):
        session_title = st.text_input(
            "Session title",
            placeholder="e.g. Setting up a Python virtual environment on Ubuntu",
        )
        error_description = st.text_area(
            "Error or challenge",
            placeholder="What went wrong? Include the exact error message or terminal traceback.",
            height=100,
        )
        solution_description = st.text_area(
            "Solution",
            placeholder="What fixed it? Record the exact commands, configuration, or steps that worked.",
            height=100,
        )
        submitted = st.form_submit_button("Save to Memory Graph", type="primary")

    if submitted:
        if not all([session_title.strip(), error_description.strip(), solution_description.strip()]):
            st.warning("Please complete all three fields.")
        else:
            try:
                with st.spinner("Creating Session, Error, and Solution nodes in FalkorDB..."):
                    saved = save_memory(
                        session_title.strip(),
                        error_description.strip(),
                        solution_description.strip(),
                        status="recorded",
                    )

                st.success("Memory saved to FalkorDB graph successfully.")
                st.markdown(f"**Session:** `{saved['session']}`")
                st.caption(f"Memory ID: `{saved['memory_id']}` · Status: Recorded · Created: {saved['created_at']}")
                st.info("The memory graph and dashboard statistics will reflect this new knowledge immediately.")

            except Exception as exc:
                st.error(f"Could not save the memory: {sanitize_error_message(str(exc))}")

# 3. SEARCH MEMORIES
elif nav_mode == "🔍 Search Memories":
    st.markdown(
        """
        <div class="workbench-header">
            <div class="workbench-header-left">
                <div class="workbench-title-row">
                    <h1 class="workbench-title">Search Graph Memories</h1>
                    <span class="workbench-tag">Cypher Search</span>
                </div>
                <div class="workbench-subtitle">
                    Weighted Cypher queries over historical sessions, errors, and verified solutions.
                </div>
            </div>
            <div class="workbench-tag">FalkorDB</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s_col1, s_col2 = st.columns([5, 1])
    with s_col1:
        keyword = st.text_input(
            "Search your developer memories",
            placeholder="Search keywords: ensurepip, git push, kafka, connection...",
            key="search_keyword",
            label_visibility="collapsed",
        )
    with s_col2:
        search_clicked = st.button("Search Graph", type="primary", use_container_width=True)

    if search_clicked or keyword.strip():
        if not keyword.strip():
            st.warning("Enter a search term.")
        else:
            try:
                with st.spinner("Executing Cypher search on FalkorDB..."):
                    memories = search_memories(keyword.strip())

                if not memories:
                    st.info(f"No matching memories found for '{keyword.strip()}'. Try another keyword.")
                else:
                    st.success(f"Found {len(memories)} matching memory record(s) in FalkorDB.")

                    for index, row in enumerate(memories, start=1):
                        title = row[0]
                        error = row[1]
                        solution = row[2]
                        created_at = row[3] if len(row) > 3 else None
                        relevance = row[4] if len(row) > 4 else 1
                        status = row[5] if len(row) > 5 else "recorded"

                        badge_text = "Verified" if status == "verified" else "Recorded"
                        with st.expander(f"{index}. {title} [{badge_text}]", expanded=(index <= 3)):
                            st.caption(f"Cypher Relevance Score: {relevance} · Status: {status.title()}")
                            st.markdown(
                                f"""
                                <div class="traversal-path" style="margin-bottom:8px;">
                                    <span class="traversal-step-session">Session: {str(title)[:28]}</span>
                                    <span class="traversal-arrow">─[:ENCOUNTERED]─▶</span>
                                    <span class="traversal-step-error">Error</span>
                                    <span class="traversal-arrow">─[:RESOLVED_BY]─▶</span>
                                    <span class="traversal-step-solution">Solution</span>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            st.markdown("**Challenge / Error Pattern:**")
                            st.code(error, language="text")
                            st.markdown("**Recorded Working Solution:**")
                            st.write(solution)
                            if created_at:
                                st.caption(f"Logged: {created_at}")
                            else:
                                st.caption("Logged date unavailable for this older record.")

            except Exception as exc:
                st.error(f"Search failed: {sanitize_error_message(str(exc))}")

# 4. MEMORY GRAPH VISUALIZATION
elif nav_mode == "🕸️ Memory Graph":
    st.markdown(
        """
        <div class="workbench-header">
            <div class="workbench-header-left">
                <div class="workbench-title-row">
                    <h1 class="workbench-title">Memory Graph Explorer</h1>
                    <span class="workbench-tag">Topology</span>
                </div>
                <div class="workbench-subtitle">
                    Connected graph paths: (Session)-[:ENCOUNTERED]->(Error)-[:RESOLVED_BY]->(Solution).
                </div>
            </div>
            <div class="workbench-tag">Interactive Topology</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        rows = get_graph_data()

        if not rows:
            st.info("No graph data in FalkorDB yet. Save a memory first.")
        else:
            nodes = {}
            edges = []

            for session_id, title, error_id, error, solution_id, solution in rows:
                nodes[session_id] = Node(
                    id=session_id,
                    label=f"Session: {str(title)[:35]}",
                    size=22,
                    color="#38bdf8",
                    shape="box",
                    font={"color": "#ffffff", "face": "monospace"},
                )

                nodes[error_id] = Node(
                    id=error_id,
                    label=f"Error: {str(error)[:42]}",
                    size=18,
                    color="#f43f5e",
                    shape="box",
                    font={"color": "#ffffff", "face": "monospace"},
                )

                nodes[solution_id] = Node(
                    id=solution_id,
                    label=f"Solution: {str(solution)[:42]}",
                    size=18,
                    color="#10b981",
                    shape="box",
                    font={"color": "#ffffff", "face": "monospace"},
                )

                edges.extend(
                    [
                        Edge(
                            source=session_id,
                            target=error_id,
                            label="ENCOUNTERED",
                            color="#64748b",
                        ),
                        Edge(
                            source=error_id,
                            target=solution_id,
                            label="RESOLVED_BY",
                            color="#64748b",
                        ),
                    ]
                )

            config = Config(
                width="100%",
                height=600,
                directed=True,
                physics=True,
                hierarchical=False,
                nodeHighlightBehavior=True,
                highlightColor="#f59e0b",
            )

            st.caption(
                f"Graph Topology: {len(rows)} memory paths · "
                f"{len(nodes)} unique nodes · {len(edges)} relationships"
            )

            agraph(
                nodes=list(nodes.values()),
                edges=edges,
                config=config,
            )

    except Exception as exc:
        st.error(f"Could not load the graph visualization: {sanitize_error_message(str(exc))}")

# -------------------- WORKSPACE FOOTER --------------------

st.markdown("---")
st.caption(
    "Developer Memory Graph · Built with Streamlit, FalkorDB Cloud Cypher Graph, & OpenRouter · "
    "WeMakeDevs Graph Hacks Hackathon Submission"
)
