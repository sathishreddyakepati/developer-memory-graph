import os
import streamlit as st
from memory import save_memory
from retrieval import search_memories, get_graph_data, get_graph_stats
from agent import (
    AgentResponse,
    ask_developer_memory_agent,
    get_configured_model,
    get_bounded_timeout,
    sanitize_error_message,
)
from streamlit_agraph import agraph, Node, Edge, Config

st.set_page_config(
    page_title="Developer Memory Graph",
    page_icon="🧠",
    layout="wide",
)

# Initialize persistent session state for agent execution
if "agent_loading" not in st.session_state:
    st.session_state["agent_loading"] = False
if "agent_response" not in st.session_state:
    st.session_state["agent_response"] = None
if "agent_last_query" not in st.session_state:
    st.session_state["agent_last_query"] = ""

# -------------------- HEADER --------------------

st.title("🧠 Developer Memory Graph")
st.caption(
    "Your development sessions, errors, and solutions — "
    "connected through FalkorDB & powered by AI Agent Memory."
)

# -------------------- DASHBOARD STATISTICS --------------------

try:
    sessions, errors, solutions, relationships = get_graph_stats()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sessions", sessions)
    col2.metric("Errors", errors)
    col3.metric("Solutions", solutions)
    col4.metric("Relationships", relationships)

except Exception as exc:
    st.warning(f"Statistics unavailable: {exc}")

st.divider()

# -------------------- TABS --------------------

tab_agent, tab_save, tab_search, tab_graph = st.tabs(
    [
        "🤖 AI Memory Agent",
        "➕ Save a Memory",
        "🔍 Search Memories",
        "🕸️ Memory Graph",
    ]
)

# -------------------- 1. AI MEMORY AGENT --------------------

with tab_agent:
    st.subheader("🤖 AI Developer Memory Agent")
    st.caption(
        "Ask a debugging question or paste an error traceback. "
        "The agent searches your team's FalkorDB knowledge graph for past solutions before synthesizing an answer."
    )

    col_meta_1, col_meta_2 = st.columns(2)
    with col_meta_1:
        st.caption("📦 **Memory Store:** FalkorDB Cloud (`developer_memory`)")
    with col_meta_2:
        model_name = get_configured_model()
        default_timeout = int(get_bounded_timeout())
        st.caption(f"⚡ **LLM Engine:** `{model_name}` (OpenRouter · {default_timeout}s timeout)")

    st.write("💡 **Quick Presets (click to test):**")
    p_col1, p_col2, p_col3 = st.columns(3)
    if p_col1.button("🐍 ensurepip venv error", use_container_width=True):
        st.session_state["agent_query_input"] = "ensurepip unavailable when creating venv"
    if p_col2.button("🐙 git push rejected", use_container_width=True):
        st.session_state["agent_query_input"] = "failed to push some refs to remote repository updates were rejected"
    if p_col3.button("🦀 kafka connection error", use_container_width=True):
        st.session_state["agent_query_input"] = "Kafka broker connection refused in Rust client on port 9092"

    query_input = st.text_area(
        "Your question or pasted traceback:",
        placeholder="e.g. ensurepip unavailable when creating venv on python3.14, or paste full terminal traceback...",
        height=130,
        key="agent_query_input",
    )

    retry_triggered = st.session_state.pop("agent_retry_trigger", False)
    consult_btn = st.button("🧠 Consult Memory Agent", type="primary", use_container_width=True)

    # Trigger agent execution
    if consult_btn or retry_triggered:
        if not query_input.strip():
            st.warning("Please enter a question or paste a traceback.")
        else:
            st.session_state["agent_loading"] = True
            st.session_state["agent_last_query"] = query_input.strip()
            try:
                with st.spinner(f"Querying FalkorDB memory graph & reasoning with {model_name}..."):
                    response = ask_developer_memory_agent(query_input.strip())
                    st.session_state["agent_response"] = response
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
                # Guaranteed: failed, timed out, or successful request ALWAYS exits loading state
                st.session_state["agent_loading"] = False

    # Render results from session state (preserves state across reruns)
    response: AgentResponse | None = st.session_state.get("agent_response")

    if response is not None:
        # 1. Independent FalkorDB Retrieval Diagnostic
        if response.retrieval_status == "error":
            st.warning(f"⚠️ **FalkorDB Retrieval Diagnostic:** Graph query encountered an error: {response.retrieval_error}")
        elif response.has_historical_evidence:
            timing_note = f" in {response.retrieval_time_seconds:.2f}s" if response.retrieval_time_seconds else ""
            st.success(
                f"✅ **FalkorDB Retrieval Diagnostic:** Grounded in {len(response.evidence)} Historical Team Memory Record(s) from FalkorDB{timing_note}"
            )
            with st.expander("📚 View Retrieved Historical Evidence from FalkorDB", expanded=(not response.success)):
                for idx, ev in enumerate(response.evidence, start=1):
                    st.markdown(f"**{idx}. Session:** {ev['session']}")
                    st.markdown(f"- **Error:** `{ev['error']}`")
                    st.markdown(f"- **Recorded Solution:** {ev['solution']}")
                    if ev.get("created_at"):
                        st.caption(f"Logged: {ev['created_at']}")
                    st.divider()
        elif response.retrieval_status == "no_matches" or (response.retrieval_status == "success" and not response.has_historical_evidence):
            st.info(
                "ℹ️ **FalkorDB Retrieval Diagnostic:** No matching historical records found in your FalkorDB memory graph for this specific issue."
            )

        # 2. LLM Inference Result & Timeout Handling
        if response.is_timeout or response.error_type == "timeout":
            timeout_display = int(response.timeout_seconds or default_timeout)
            timing_note = f" (elapsed: {response.inference_time_seconds:.1f}s)" if response.inference_time_seconds else ""
            st.error(
                f"⏱️ **OpenRouter Inference Timeout ({timeout_display}s{timing_note})**\n\n"
                f"{response.error_message}\n\n"
                "The upstream OpenRouter model queue or provider took longer than the allotted timeout to answer. "
                "Notice above that your FalkorDB graph retrieval succeeded independently."
            )
            col_retry, col_retry_info = st.columns([1, 3])

            def _trigger_retry():
                st.session_state["agent_retry_trigger"] = True

            with col_retry:
                st.button("🔄 Retry OpenRouter Inference", type="primary", key="retry_agent_btn", on_click=_trigger_retry)
            with col_retry_info:
                st.caption("Click to trigger a retry. Retries are strictly manual (no automatic infinite retries).")

        elif not response.success:
            st.error(f"❌ **Agent Request Failed:** {response.error_message}")
            if response.error_type == "auth_missing":
                st.info("Tip: Set `OPENROUTER_API_KEY` in your `.env` file.")
            else:
                def _trigger_generic_retry():
                    st.session_state["agent_retry_trigger"] = True

                col_retry, _ = st.columns([1, 3])
                with col_retry:
                    st.button("🔄 Retry Request", key="retry_generic_btn", on_click=_trigger_generic_retry)

        else:
            # Grounded Response
            st.markdown(response.answer)

            st.warning(
                "⚠️ **Safety Notice:** Review all code snippets and shell commands carefully. "
                "Commands are never executed automatically by the agent."
            )

            # Interactive Save Form (Requirement 13)
            st.divider()
            st.subheader("✅ Did this fix work?")
            st.write(
                "If you tested this solution and it worked, record it to your team's FalkorDB "
                "memory graph so developers and agents can reuse it in future sessions:"
            )

            with st.expander("💾 Confirm & Save Verified Solution to Memory Graph"):
                with st.form("confirm_save_form", clear_on_submit=True):
                    active_query = st.session_state.get("agent_last_query", query_input)
                    first_line = active_query.strip().splitlines()[0][:50] if active_query.strip() else "Verified Solution"
                    save_title = st.text_input("Session Title", value=f"Fix: {first_line}")
                    save_error = st.text_area("Error / Challenge", value=active_query.strip()[:400])
                    save_solution = st.text_area(
                        "Working Solution Verified by You",
                        placeholder="Enter the specific command or configuration step that fixed the problem...",
                    )
                    save_submit = st.form_submit_button("Save Verified Solution to Graph", type="primary")

                if save_submit:
                    if not all([save_title.strip(), save_error.strip(), save_solution.strip()]):
                        st.warning("Please complete all three fields to save the verified memory.")
                    else:
                        try:
                            saved_res = save_memory(
                                save_title.strip(),
                                save_error.strip(),
                                save_solution.strip(),
                            )
                            st.success(f"Verified memory saved! Memory ID: {saved_res['memory_id']}")
                            st.info("The dashboard statistics will update on next rerun.")
                        except Exception as save_err:
                            st.error(f"Could not save memory: {save_err}")

# -------------------- 2. SAVE MEMORY (ORIGINAL) --------------------

with tab_save:
    st.subheader("Capture a development experience")
    st.write("Record a problem and the solution that worked.")

    with st.form("save_memory_form", clear_on_submit=True):
        session_title = st.text_input(
            "Session title",
            placeholder="e.g. Setting up a Python environment",
        )

        error_description = st.text_area(
            "Error or challenge",
            placeholder="What went wrong? Include the error message if available.",
        )

        solution_description = st.text_area(
            "Solution",
            placeholder="What fixed it? Record the steps that worked.",
        )

        submitted = st.form_submit_button(
            "Save to Memory Graph",
            type="primary",
        )

    if submitted:
        if not all(
            [
                session_title.strip(),
                error_description.strip(),
                solution_description.strip(),
            ]
        ):
            st.warning("Please complete all three fields.")
        else:
            try:
                with st.spinner("Saving to FalkorDB..."):
                    saved = save_memory(
                        session_title.strip(),
                        error_description.strip(),
                        solution_description.strip(),
                    )

                st.success("Memory saved successfully!")
                st.write("**Session:**", saved["session"])
                st.caption(f"Memory ID: {saved['memory_id']}")
                st.info(
                    "Your memory is saved. The dashboard statistics "
                    "will refresh when the app reruns."
                )

            except Exception as exc:
                st.error(f"Could not save the memory: {exc}")

# -------------------- 3. SEARCH MEMORIES (ORIGINAL) --------------------

with tab_search:
    st.subheader("Recall a previous solution")
    st.write("Search past development sessions, errors, and solutions.")

    keyword = st.text_input(
        "Search your developer memories",
        placeholder="Try: Python, connection, ensurepip...",
        key="search_keyword",
    )

    if st.button("Search Graph", type="primary"):
        if not keyword.strip():
            st.warning("Enter a search term.")
        else:
            try:
                with st.spinner("Searching FalkorDB..."):
                    memories = search_memories(keyword.strip())

                if not memories:
                    st.info("No matching memories found. Try another keyword.")
                else:
                    st.success(
                        f"Found {len(memories)} matching memories."
                    )

                    for index, row in enumerate(memories, start=1):
                        title, error, solution, created_at, relevance = row

                        with st.expander(f"{index}. {title}"):
                            st.caption(f"Relevance score: {relevance}")

                            st.markdown("**Challenge / Error**")
                            st.write(error)

                            st.markdown("**Recorded Solution**")
                            st.write(solution)

                            if created_at:
                                st.caption(f"Recorded: {created_at}")
                            else:
                                st.caption(
                                    "Recorded date unavailable for "
                                    "this older memory."
                                )

            except Exception as exc:
                st.error(f"Search failed: {exc}")

# -------------------- 4. GRAPH VISUALIZATION (ORIGINAL) --------------------

with tab_graph:
    st.subheader("Explore your developer memory graph")
    st.write(
        "Follow the connections from a development session "
        "to the error and its recorded solution."
    )

    try:
        rows = get_graph_data()

        if not rows:
            st.info("No graph data yet. Save a memory first.")
        else:
            nodes = {}
            edges = []

            for session_id, title, error_id, error, solution_id, solution in rows:
                nodes[session_id] = Node(
                    id=session_id,
                    label=f"Session: {str(title)[:35]}",
                    size=25,
                    color="#4F8EF7",
                    shape="box",
                )

                nodes[error_id] = Node(
                    id=error_id,
                    label=f"Error: {str(error)[:45]}",
                    size=22,
                    color="#F06565",
                    shape="box",
                )

                nodes[solution_id] = Node(
                    id=solution_id,
                    label=f"Solution: {str(solution)[:45]}",
                    size=22,
                    color="#38B878",
                    shape="box",
                )

                edges.extend(
                    [
                        Edge(
                            source=session_id,
                            target=error_id,
                            label="ENCOUNTERED",
                            color="#9CA3AF",
                        ),
                        Edge(
                            source=error_id,
                            target=solution_id,
                            label="RESOLVED_BY",
                            color="#9CA3AF",
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
                highlightColor="#F59E0B",
            )

            st.caption(
                f"{len(rows)} memory paths · "
                f"{len(nodes)} nodes · {len(edges)} relationships"
            )

            agraph(
                nodes=list(nodes.values()),
                edges=edges,
                config=config,
            )

    except Exception as exc:
        st.error(f"Could not load the graph: {exc}")

# -------------------- FOOTER --------------------

st.divider()
st.caption(
    "Developer Memory Graph | Python · Streamlit · Cypher · FalkorDB Cloud · OpenRouter"
)
