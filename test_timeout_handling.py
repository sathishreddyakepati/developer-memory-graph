"""
Unit and regression tests for OpenRouter inference timeout handling,
direct requests.post timeout tuple, safe diagnostic logging, credential protection,
independent diagnosability, thread safety, and Streamlit loading-state lifecycles.

These tests use unittest.mock and Streamlit AppTest without making live
external API calls and without modifying FalkorDB graph data.
"""

import concurrent.futures
import io
import logging
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import requests

from agent import (
    DEFAULT_MODEL,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    AgentResponse,
    ask_developer_memory_agent,
    call_openrouter_api,
    get_bounded_timeout,
    get_configured_model,
    sanitize_error_message,
)


class TestTimeoutHandling(unittest.TestCase):

    def setUp(self):
        self.mock_evidence = [
            {
                "session": "WSL Python environment setup",
                "error": "ensurepip unavailable when creating venv",
                "solution": "Install python3.14-venv and recreate the virtual environment",
                "created_at": "2026-10-16T12:00:00Z",
                "relevance": 6,
                "matched_term": "ensurepip",
            }
        ]

    # ---------------- 1. BOUNDED TIMEOUT TESTS ----------------

    def test_bounded_timeout_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            timeout = get_bounded_timeout(None)
            self.assertEqual(timeout, DEFAULT_REQUEST_TIMEOUT_SECONDS)
            self.assertGreaterEqual(timeout, MIN_TIMEOUT_SECONDS)
            self.assertLessEqual(timeout, MAX_TIMEOUT_SECONDS)

    def test_bounded_timeout_clamps_lower_bound(self):
        self.assertEqual(get_bounded_timeout(0), MIN_TIMEOUT_SECONDS)
        self.assertEqual(get_bounded_timeout(-10), MIN_TIMEOUT_SECONDS)
        self.assertEqual(get_bounded_timeout(2.5), MIN_TIMEOUT_SECONDS)

    def test_bounded_timeout_clamps_upper_bound(self):
        self.assertEqual(get_bounded_timeout(300), MAX_TIMEOUT_SECONDS)
        self.assertEqual(get_bounded_timeout(9999), MAX_TIMEOUT_SECONDS)

    def test_bounded_timeout_valid_range(self):
        self.assertEqual(get_bounded_timeout(45), 45.0)
        self.assertEqual(get_bounded_timeout(15.5), 15.5)

    def test_bounded_timeout_from_environment(self):
        with patch.dict(os.environ, {"OPENROUTER_TIMEOUT": "50"}):
            self.assertEqual(get_bounded_timeout(None), 50.0)

        with patch.dict(os.environ, {"OPENROUTER_TIMEOUT": "500"}):
            self.assertEqual(get_bounded_timeout(None), MAX_TIMEOUT_SECONDS)

        with patch.dict(os.environ, {"OPENROUTER_TIMEOUT": "invalid_num"}):
            self.assertEqual(get_bounded_timeout(None), DEFAULT_REQUEST_TIMEOUT_SECONDS)

    # ---------------- 2. MODEL CONFIGURATION TESTS ----------------

    def test_model_id_read_from_openrouter_model(self):
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "custom-org/custom-model:latest"}):
            model = get_configured_model()
            self.assertEqual(model, "custom-org/custom-model:latest")

    def test_model_id_fallback_when_unset(self):
        with patch.dict(os.environ, {"OPENROUTER_MODEL": ""}):
            model = get_configured_model()
            self.assertEqual(model, DEFAULT_MODEL)

    # ---------------- 3. CREDENTIAL SANITIZATION TESTS ----------------

    def test_sanitize_error_message_redacts_api_key(self):
        fake_key = "sk-or-v1-secret1234567890abcdef"
        msg = f"Failed to connect using key {fake_key} to endpoint"
        sanitized = sanitize_error_message(msg, api_key=fake_key)
        self.assertNotIn(fake_key, sanitized)
        self.assertIn("[REDACTED_KEY]", sanitized)

    def test_sanitize_error_message_redacts_bearer_token(self):
        msg = "Error: Bearer sk-or-v1-abcdef123456 rejected"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("sk-or-v1-abcdef123456", sanitized)
        self.assertIn("Bearer [REDACTED]", sanitized)

    def test_sanitize_error_message_redacts_auth_headers(self):
        msg = "Request headers: {'Authorization': 'Bearer sk-or-v1-supersecret', 'Accept': 'json'}"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("sk-or-v1-supersecret", sanitized)
        self.assertIn("'Authorization': '[REDACTED]'", sanitized)

    # ---------------- 4. REQUESTS.TIMEOUT & NON-BLOCKING EXECUTION ----------------

    @patch("agent.requests.post")
    def test_call_openrouter_api_raises_requests_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out after 30s")

        with self.assertRaises(requests.Timeout) as ctx:
            call_openrouter_api(
                user_prompt="test prompt",
                evidence_text="test evidence",
                model="test/model",
                api_key="sk-test-key",
                timeout=30,
            )

        self.assertIn("timed out after 30 seconds", str(ctx.exception))
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        # Connect timeout is capped to min(5.0, bounded_timeout), read timeout is 30s
        self.assertEqual(kwargs["timeout"], (5.0, 30.0))

    @patch("concurrent.futures.ThreadPoolExecutor")
    @patch("agent.requests.post")
    def test_timeout_returns_control_without_executor_shutdown_delay(
        self, mock_post, mock_executor
    ):
        """
        Verify that timeout handling returns control immediately without blocking
        on a ThreadPoolExecutor context-manager shutdown or creating worker threads.
        """
        initial_threads = threading.active_count()
        mock_post.side_effect = requests.exceptions.Timeout("Read timed out")

        t0 = time.time()
        with self.assertRaises(requests.Timeout) as ctx:
            call_openrouter_api(
                user_prompt="test",
                evidence_text="test",
                model="test",
                api_key="sk-test",
                timeout=30.0,
            )
        elapsed = time.time() - t0

        # Control returns immediately without executor context manager shutdown delays
        self.assertLess(elapsed, 0.5)
        self.assertIn("timed out after 30 seconds", str(ctx.exception))

        # ThreadPoolExecutor is NOT used
        mock_executor.assert_not_called()

        # Thread count has not increased
        self.assertEqual(threading.active_count(), initial_threads)

    @patch("agent.requests.post")
    def test_no_background_threads_accumulate_after_timed_out_requests(self, mock_post):
        """
        Verify that multiple timed-out requests do not leave background threads
        accumulating in the process.
        """
        initial_threads = threading.active_count()
        mock_post.side_effect = requests.exceptions.Timeout("Socket read timed out")

        for _ in range(5):
            with self.assertRaises(requests.Timeout):
                call_openrouter_api(
                    user_prompt="test query",
                    evidence_text="test evidence",
                    model="nvidia/nemotron-3.5-lightning:free",
                    api_key="sk-test-key",
                    timeout=10.0,
                )

        # Thread count must remain strictly unchanged across multiple timeouts
        self.assertEqual(threading.active_count(), initial_threads)

    @patch("agent.call_openrouter_api")
    @patch("agent.retrieve_relevant_memories")
    def test_ask_developer_memory_agent_handles_timeout_separately(
        self, mock_retrieve, mock_call_api
    ):
        mock_retrieve.return_value = self.mock_evidence
        mock_call_api.side_effect = requests.Timeout("OpenRouter inference timed out after 30 seconds.")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-testkey", "OPENROUTER_MODEL": "nvidia/nemotron-3.5-lightning:free"}):
            response: AgentResponse = ask_developer_memory_agent("ensurepip unavailable")

            self.assertFalse(response.success)
            self.assertTrue(response.is_timeout)
            self.assertEqual(response.error_type, "timeout")
            self.assertEqual(response.inference_status, "timeout")
            self.assertIn("timed out after 30 seconds", response.error_message)
            self.assertEqual(response.timeout_seconds, 30.0)

    # ---------------- 5. INDEPENDENT DIAGNOSABILITY ----------------

    @patch("agent.call_openrouter_api")
    @patch("agent.retrieve_relevant_memories")
    def test_falkordb_retrieval_and_llm_inference_independently_diagnosable(
        self, mock_retrieve, mock_call_api
    ):
        mock_retrieve.return_value = self.mock_evidence
        mock_call_api.side_effect = requests.Timeout("Timed out waiting for upstream LLM")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-testkey"}):
            response = ask_developer_memory_agent("ensurepip error")

            self.assertEqual(response.retrieval_status, "success")
            self.assertIsNone(response.retrieval_error)
            self.assertTrue(response.has_historical_evidence)
            self.assertEqual(len(response.evidence), 1)
            self.assertEqual(response.evidence[0]["session"], "WSL Python environment setup")

            self.assertEqual(response.inference_status, "timeout")
            self.assertTrue(response.is_timeout)
            self.assertFalse(response.success)

    @patch("agent.call_openrouter_api")
    @patch("agent.retrieve_relevant_memories")
    def test_falkordb_failure_diagnosed_independently_from_llm(
        self, mock_retrieve, mock_call_api
    ):
        def simulate_retrieval_failure(query, limit=5, error_collector=None):
            if error_collector is not None:
                error_collector.append(ConnectionError("FalkorDB host unreachable"))
            return []

        mock_retrieve.side_effect = simulate_retrieval_failure
        mock_call_api.return_value = "### 🛠️ 2. Diagnosis\nGeneral advice"

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-v1-testkey"}):
            response = ask_developer_memory_agent("some unknown error")

            self.assertEqual(response.retrieval_status, "error")
            self.assertIn("FalkorDB query failed", response.retrieval_error)
            self.assertFalse(response.has_historical_evidence)
            self.assertTrue(response.success)
            self.assertEqual(response.inference_status, "success")

    # ---------------- 6. SAFE DIAGNOSTIC LOGGING ----------------

    @patch("agent.call_openrouter_api")
    @patch("agent.retrieve_relevant_memories")
    def test_safe_diagnostic_logging_contains_no_secrets(self, mock_retrieve, mock_call_api):
        mock_retrieve.return_value = self.mock_evidence
        mock_call_api.return_value = "Answer content"

        fake_secret_key = "sk-or-v1-supersecretkey999"
        log_stream = io.StringIO()
        agent_logger = logging.getLogger("developer_memory.agent")
        stream_handler = logging.StreamHandler(log_stream)
        agent_logger.addHandler(stream_handler)

        try:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": fake_secret_key}):
                ask_developer_memory_agent("test query")

            log_output = log_stream.getvalue()
            # Must log retrieval and inference milestones
            self.assertIn("FalkorDB retrieval starting", log_output)
            self.assertIn("FalkorDB retrieval succeeded", log_output)
            self.assertIn("Starting LLM inference with OpenRouter", log_output)
            self.assertIn("LLM inference succeeded", log_output)
            # Must NEVER contain the secret key
            self.assertNotIn(fake_secret_key, log_output)
            self.assertNotIn("Bearer", log_output)
        finally:
            agent_logger.removeHandler(stream_handler)

    # ---------------- 7. NO AUTOMATIC INFINITE RETRIES ----------------

    @patch("agent.requests.post")
    def test_single_request_executed_without_infinite_retry(self, mock_post):
        mock_post.side_effect = requests.Timeout("Timeout")

        with self.assertRaises(requests.Timeout):
            call_openrouter_api(
                user_prompt="test",
                evidence_text="test",
                model="test",
                api_key="sk-test",
                timeout=10,
            )

        self.assertEqual(mock_post.call_count, 1)

    # ---------------- 8. READ-ONLY VALIDATION ----------------

    def test_agent_never_imports_or_calls_save_memory(self):
        import agent
        self.assertFalse(hasattr(agent, "save_memory"))

    # ---------------- 9. REGRESSION: STREAMLIT LOADING-STATE EXITS ON TIMEOUT ----------------

    def test_streamlit_loading_state_clears_on_timeout(self):
        """
        Regression test: When OpenRouter inference times out, the app MUST:
        1. Set agent_loading = False (never permanently stuck in loading state).
        2. Set agent_response with is_timeout=True.
        3. Render the timeout alert.
        4. Render the independent FalkorDB retrieval diagnostic.
        5. Render the user-triggered retry button.
        """
        from streamlit.testing.v1 import AppTest

        with patch("retrieval.get_graph_stats", return_value=(6, 6, 6, 12)), \
             patch("retrieval.get_graph_data", return_value=[]), \
             patch("agent.ask_developer_memory_agent") as mock_agent:

            mock_agent.return_value = AgentResponse(
                success=False,
                answer="",
                evidence=self.mock_evidence,
                has_historical_evidence=True,
                model_used="nvidia/nemotron-3.5-lightning:free",
                error_type="timeout",
                error_message="OpenRouter inference timed out after 30 seconds.",
                retrieval_status="success",
                retrieval_time_seconds=1.8,
                inference_status="timeout",
                inference_time_seconds=30.0,
                timeout_seconds=30.0,
                is_timeout=True,
            )

            at = AppTest.from_file("/home/sathish/developer-memory-graph/app.py", default_timeout=15).run()
            self.assertFalse(at.exception)
            self.assertFalse(at.session_state["agent_loading"])

            # Set user query
            at.text_area[0].input("ensurepip unavailable").run()
            self.assertFalse(at.exception)

            # Click consult button
            consult_button = [b for b in at.button if "Consult" in b.label][0]
            consult_button.click().run()

            self.assertFalse(at.exception)
            self.assertEqual(mock_agent.call_count, 1)

            # CRITICAL REGRESSION ASSERTION: agent_loading MUST be False after execution
            self.assertFalse(at.session_state["agent_loading"])
            self.assertIsNotNone(at.session_state["agent_response"])
            self.assertTrue(at.session_state["agent_response"].is_timeout)

            # Check that timeout error banner is displayed
            error_texts = [e.value for e in at.error]
            self.assertTrue(any("OpenRouter Inference Timeout" in err for err in error_texts))

            # Check that independent FalkorDB retrieval diagnosis is displayed
            success_texts = [s.value for s in at.success]
            self.assertTrue(any("FalkorDB Retrieval Diagnostic" in s for s in success_texts))

            # Check that user-triggered retry button is shown
            retry_buttons = [b for b in at.button if "Retry OpenRouter Inference" in b.label]
            self.assertEqual(len(retry_buttons), 1)

            # Trigger retry
            retry_buttons[0].click().run()
            self.assertFalse(at.exception)
            # Exactly one retry execution triggered by user click (call_count becomes 2)
            self.assertEqual(mock_agent.call_count, 2)
            # CRITICAL REGRESSION ASSERTION: agent_loading MUST be False after retry too
            self.assertFalse(at.session_state["agent_loading"])

    # ---------------- 10. REGRESSION: STREAMLIT LOADING-STATE EXITS ON UNHANDLED EXCEPTION ----------------

    def test_streamlit_loading_state_clears_on_unhandled_exception(self):
        """
        Regression test: If an unexpected error occurs, the app MUST NOT remain
        in a permanent loading state, and MUST display the error.
        """
        from streamlit.testing.v1 import AppTest

        with patch("retrieval.get_graph_stats", return_value=(6, 6, 6, 12)), \
             patch("retrieval.get_graph_data", return_value=[]), \
             patch("agent.ask_developer_memory_agent") as mock_agent:

            mock_agent.side_effect = RuntimeError("Simulated unexpected crash during agent execution")

            at = AppTest.from_file("/home/sathish/developer-memory-graph/app.py", default_timeout=15).run()
            at.text_area[0].input("test crash query").run()

            consult_button = [b for b in at.button if "Consult" in b.label][0]
            consult_button.click().run()

            # Must not have crashed the script runner
            self.assertFalse(at.exception)
            # Loading state must be cleanly cleared
            self.assertFalse(at.session_state["agent_loading"])
            # Error must be shown
            error_texts = [e.value for e in at.error]
            self.assertTrue(any("Simulated unexpected crash" in err for err in error_texts))


if __name__ == "__main__":
    unittest.main()
