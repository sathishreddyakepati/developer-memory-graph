import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import requests
from dotenv import load_dotenv

from retrieval import search_memories

# Ensure environment variables are loaded
load_dotenv()

# Safe diagnostic logger - never logs secrets
logger = logging.getLogger("developer_memory.agent")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [agent] %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning:free"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
MIN_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 120.0
REQUEST_TIMEOUT_SECONDS = int(DEFAULT_REQUEST_TIMEOUT_SECONDS)

SYSTEM_PROMPT = """You are the AI Developer Memory Agent for a software engineering team.
You are directly integrated with the team's FalkorDB Developer Memory Graph, which stores past development sessions, encountered errors, and verified solutions.

When answering developer inquiries or diagnosing tracebacks, adhere strictly to the following principles:

1. GROUNDING & EVIDENCE:
   - Carefully review the provided 'Retrieved Historical Memories (from FalkorDB)'.
   - If a retrieved memory matches the developer's error or technology stack, prioritize that verified team solution. Explicitly cite the session title, error description, and past solution.
   - If NO retrieved memories are relevant (or if the only retrieved items are superficial word overlaps with unrelated tools), explicitly state:
     "⚠️ No relevant historical records found in your FalkorDB memory graph for this specific issue."
   - Never claim an issue was in the team memory graph if it was not.

2. STRUCTURED RESPONSE FORMAT:
   Format your response with the following clearly labeled markdown sections:

   ### 📚 1. Historical Team Evidence (from FalkorDB Memory Graph)
   (State what past sessions in FalkorDB recorded, or state that no relevant records exist.)

   ### 🛠️ 2. Diagnosis & Recommended Action Plan
   (Provide the precise root cause and step-by-step resolution with code/terminal commands.)

   ### ⚠️ 3. Limitations & Verification Advice
   (State environment assumptions, compatibility caveats, and remind the developer to test the fix.)

3. SAFETY & ACCURACY:
   - Provide command snippets in standard code blocks for the developer to inspect and execute manually.
   - Do NOT assume external dependencies or versions unless specified.
"""


def sanitize_error_message(message: str, api_key: Optional[str] = None) -> str:
    """
    Ensure API keys, authorization tokens, or Bearer credentials are never leaked
    in error messages, logs, or UI elements.
    """
    if not message:
        return ""
    sanitized = str(message)

    # Redact explicit api_key parameter
    if api_key and len(api_key.strip()) > 3:
        sanitized = sanitized.replace(api_key.strip(), "[REDACTED_KEY]")

    # Redact environment secrets if present
    env_openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_openrouter_key and len(env_openrouter_key) > 3:
        sanitized = sanitized.replace(env_openrouter_key, "[REDACTED_KEY]")

    env_falkordb_pw = os.environ.get("FALKORDB_PASSWORD", "").strip()
    if env_falkordb_pw and len(env_falkordb_pw) > 3:
        sanitized = sanitized.replace(env_falkordb_pw, "[REDACTED_PASSWORD]")

    # Redact Bearer tokens: Bearer <token>
    sanitized = re.sub(r"Bearer\s+[\w\-\.]+", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)

    # Redact Authorization header strings or dict entries
    sanitized = re.sub(
        r"['\"]?Authorization['\"]?\s*:\s*['\"][^'\"]+['\"]",
        "'Authorization': '[REDACTED]'",
        sanitized,
        flags=re.IGNORECASE,
    )

    # Redact common key formats (sk-or-v1-..., sk-...)
    sanitized = re.sub(r"sk-(or-)?v1-[a-zA-Z0-9_\-]+", "[REDACTED_KEY]", sanitized)

    return sanitized


def get_bounded_timeout(timeout: Optional[Union[int, float]] = None) -> float:
    """
    Return a strictly bounded timeout in seconds (float).
    Falls back to OPENROUTER_TIMEOUT environment variable, then DEFAULT_REQUEST_TIMEOUT_SECONDS.
    Guarantees MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS.
    Never returns None or an unbounded value.
    """
    if timeout is None:
        env_val = os.environ.get("OPENROUTER_TIMEOUT", "").strip()
        if env_val:
            try:
                timeout = float(env_val)
            except (ValueError, TypeError):
                timeout = float(DEFAULT_REQUEST_TIMEOUT_SECONDS)
        else:
            timeout = float(DEFAULT_REQUEST_TIMEOUT_SECONDS)

    try:
        val = float(timeout)
    except (ValueError, TypeError):
        val = float(DEFAULT_REQUEST_TIMEOUT_SECONDS)

    if val < MIN_TIMEOUT_SECONDS:
        return float(MIN_TIMEOUT_SECONDS)
    if val > MAX_TIMEOUT_SECONDS:
        return float(MAX_TIMEOUT_SECONDS)
    return val


def get_configured_model() -> str:
    """
    Read model ID from OPENROUTER_MODEL environment variable.
    Do not hardcode a replacement. Falls back to DEFAULT_MODEL only if unset.
    """
    env_model = os.environ.get("OPENROUTER_MODEL", "").strip()
    return env_model if env_model else DEFAULT_MODEL


@dataclass
class AgentResponse:
    success: bool
    answer: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    has_historical_evidence: bool = False
    model_used: str = ""
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    # Independent diagnostic fields
    retrieval_status: str = "success"  # "success" | "no_matches" | "error" | "skipped"
    retrieval_error: Optional[str] = None
    retrieval_time_seconds: Optional[float] = None
    inference_status: str = "success"  # "success" | "timeout" | "error" | "skipped"
    inference_error: Optional[str] = None
    inference_time_seconds: Optional[float] = None
    timeout_seconds: Optional[float] = None
    is_timeout: bool = False


def extract_search_terms(text: str) -> List[str]:
    """
    Extract meaningful search terms and phrases from a user query or traceback.
    """
    terms: List[str] = []
    cleaned = text.strip()
    if not cleaned:
        return terms

    # If it's a short query without linebreaks, include it as primary term
    if len(cleaned) < 80 and "\n" not in cleaned:
        terms.append(cleaned)

    # Extract lines containing common error or exception identifiers
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    for line in lines:
        if any(kw in line for kw in ["Error:", "Exception:", "failed to", "fatal:", "error", "rejected"]):
            # Split off common exception prefixes
            parts = re.split(r"[:\-]\s*", line)
            for part in parts:
                p_clean = part.strip()
                if 4 < len(p_clean) < 100:
                    terms.append(p_clean)

    # Tokenize words, filtering out common stop words
    words = re.findall(r"[a-zA-Z0-9_\-\.]{4,}", cleaned)
    stop_words = {
        "the", "and", "for", "with", "from", "when", "that", "this",
        "what", "have", "were", "your", "about", "some", "could", "would",
        "traceback", "file", "line", "most", "recent", "call", "last",
        "please", "help", "cant", "cannot", "getting", "here", "there",
        "error", "issue", "problem", "using", "trying"
    }
    meaningful = [w for w in words if w.lower() not in stop_words]
    terms.extend(meaningful)

    # Deduplicate while preserving order
    return list(dict.fromkeys(terms))


def retrieve_relevant_memories(
    query: str,
    limit: int = 5,
    error_collector: Optional[List[Exception]] = None,
) -> List[Dict[str, Any]]:
    """
    Search FalkorDB for memories matching the query or extracted terms.
    Filters out superficial false positives.
    Collects any underlying FalkorDB exceptions into error_collector if provided.
    """
    terms = extract_search_terms(query)
    if not terms:
        return []

    results: List[Dict[str, Any]] = []
    seen = set()

    # Query terms in order of priority
    for term in terms[:8]:
        try:
            rows = search_memories(term)
            for row in rows:
                title = row[0]
                error_desc = row[1]
                sol_desc = row[2]
                created_at = row[3] if len(row) > 3 else None
                relevance = row[4] if len(row) > 4 else 1
                status = row[5] if len(row) > 5 else "recorded"

                key = (title, error_desc, sol_desc)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "session": title,
                        "error": error_desc,
                        "solution": sol_desc,
                        "created_at": created_at,
                        "relevance": relevance,
                        "matched_term": term,
                        "status": status,
                    })
                    if len(results) >= limit:
                        break
        except Exception as exc:
            if error_collector is not None:
                error_collector.append(exc)
            continue

        if len(results) >= limit:
            break

    # Relevance check: if the query has specific technology terms (e.g. kafka, rust, redis, git, python, venv)
    # verify that the matched memory error/session shares at least some domain context
    tech_keywords = re.findall(r"[a-zA-Z0-9]{3,}", query.lower())
    high_value_keywords = {
        w for w in tech_keywords
        if w not in {"error", "code", "fail", "failed", "when", "with", "have", "some", "cant", "connect", "connection"}
    }

    if high_value_keywords:
        filtered = []
        for r in results:
            item_text = f"{r['session']} {r['error']} {r['solution']}".lower()
            if any(hw in item_text for hw in high_value_keywords):
                filtered.append(r)
        # If high value keywords existed and filtered out everything, results are truly 0
        if not filtered and results:
            # Check if matched term was merely a generic stopword-like match (e.g., 'connection')
            if all(r["matched_term"].lower() in {"connection", "client", "setup", "server"} for r in results):
                return []
        return filtered if filtered else results

    return results


def call_openrouter_api(
    user_prompt: str,
    evidence_text: str,
    model: str,
    api_key: str,
    timeout: Optional[Union[int, float]] = None,
) -> str:
    """
    Execute a chat completion request against OpenRouter using bounded connect/read timeouts.
    Uses requests.post() directly with a (connect_timeout, read_timeout) tuple:
    - connect_timeout is capped to min(5.0, bounded_timeout)
    - read_timeout is bounded_timeout

    Note: While a Requests connect/read timeout tuple does not guarantee a strict
    total wall-clock deadline across multiple read chunks or keep-alive packets,
    it avoids blocking thread-pool executor context-manager shutdowns and avoids
    creating or leaking background threads after timed-out requests.

    Handles requests.Timeout separately.
    Never exposes credentials in error messages or logs.
    Does not perform automatic infinite retries.
    """
    bounded_timeout = get_bounded_timeout(timeout)
    connect_timeout = min(5.0, bounded_timeout)
    socket_timeout = (connect_timeout, bounded_timeout)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/developer-memory-graph",
        "X-Title": "Developer Memory Graph",
    }

    user_message = f"""DEVELOPER ISSUE / QUESTION:
{user_prompt}

{evidence_text}

Please analyze this issue and generate a grounded, structured answer."""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
    }

    logger.info(
        "Starting OpenRouter HTTP request: model='%s', timeout=%.1fs (connect=%.1fs)",
        model,
        bounded_timeout,
        connect_timeout,
    )
    t_start = time.time()

    try:
        response = requests.post(
            OPENROUTER_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=socket_timeout,
        )
    except requests.Timeout as exc:
        elapsed = time.time() - t_start
        logger.warning(
            "OpenRouter request timed out after %.2fs: %s",
            elapsed,
            type(exc).__name__,
        )
        raise requests.Timeout(
            f"OpenRouter inference timed out after {bounded_timeout:.0f} seconds. "
            "The model endpoint may be congested or experiencing high queue latency. "
            "Please try again."
        ) from None
    except requests.exceptions.ConnectionError:
        elapsed = time.time() - t_start
        logger.error("Could not connect to OpenRouter after %.2fs", elapsed)
        raise ConnectionError(
            "Could not connect to OpenRouter. Please check your network connection and DNS settings."
        ) from None
    except requests.exceptions.RequestException as e:
        elapsed = time.time() - t_start
        logger.error("OpenRouter network error after %.2fs: %s", elapsed, type(e).__name__)
        safe_msg = sanitize_error_message(
            f"Network error while communicating with OpenRouter: {type(e).__name__}",
            api_key=api_key,
        )
        raise RuntimeError(safe_msg) from None

    elapsed = time.time() - t_start
    logger.info("OpenRouter HTTP response received in %.2fs (status=%d)", elapsed, response.status_code)

    # Handle HTTP status codes gracefully
    if response.status_code in (401, 403):
        raise PermissionError(
            "OpenRouter authentication failed (HTTP 401/403). "
            "Please check that OPENROUTER_API_KEY is correctly set in your .env file."
        )
    elif response.status_code == 429:
        raise RuntimeError(
            "OpenRouter rate limit reached (HTTP 429). "
            "Please wait a few moments before submitting another request."
        )
    elif response.status_code == 402:
        raise RuntimeError(
            "OpenRouter credit limit reached (HTTP 402). "
            "Please verify your account credits or switch to a free model."
        )
    elif response.status_code >= 500:
        raise RuntimeError(
            f"OpenRouter server error (HTTP {response.status_code}). "
            "The upstream service is experiencing issues. Please try again shortly."
        )
    elif response.status_code != 200:
        raise RuntimeError(
            f"OpenRouter returned unexpected status HTTP {response.status_code}."
        )

    # Parse JSON response
    try:
        data = response.json()
    except Exception:
        raise ValueError("OpenRouter returned a non-JSON or malformed response body.")

    choices = data.get("choices", [])
    if not choices or not isinstance(choices, list):
        raise ValueError("OpenRouter returned a response with no choices.")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("OpenRouter returned an empty message content.")

    return content


def ask_developer_memory_agent(
    query_or_traceback: str,
    timeout: Optional[Union[int, float]] = None,
) -> AgentResponse:
    """
    Main entry point for the Developer Memory Agent.
    1. Validates inputs and environment configuration.
    2. Retrieves relevant memories from FalkorDB (diagnosed independently with safe logging).
    3. Queries the LLM via OpenRouter with bounded timeout and safe diagnostic logging.
    4. Catches requests.Timeout separately and provides clear diagnostic statuses.
    5. Never exposes credentials.
    6. Does not perform automatic infinite retries.
    """
    cleaned_query = query_or_traceback.strip()
    if not cleaned_query:
        return AgentResponse(
            success=False,
            error_type="validation",
            error_message="Query cannot be empty. Please enter a question or paste a traceback.",
            retrieval_status="skipped",
            inference_status="skipped",
        )

    bounded_timeout = get_bounded_timeout(timeout)
    model = get_configured_model()
    terms = extract_search_terms(cleaned_query)

    # Step 1: Retrieve memories from FalkorDB (independently diagnosable)
    logger.info(
        "FalkorDB retrieval starting for query (chars=%d, terms=%d)",
        len(cleaned_query),
        len(terms),
    )
    t_ret_start = time.time()
    retrieval_errors: List[Exception] = []

    try:
        evidence = retrieve_relevant_memories(cleaned_query, error_collector=retrieval_errors)
    except Exception as ret_exc:
        retrieval_errors.append(ret_exc)
        evidence = []

    retrieval_time = time.time() - t_ret_start
    has_historical_evidence = len(evidence) > 0

    if retrieval_errors and not evidence:
        retrieval_status = "error"
        retrieval_error = sanitize_error_message(
            f"FalkorDB query failed: {type(retrieval_errors[0]).__name__} - {retrieval_errors[0]}"
        )
        logger.error(
            "FalkorDB retrieval failed after %.2fs: %s",
            retrieval_time,
            type(retrieval_errors[0]).__name__,
        )
    elif has_historical_evidence:
        retrieval_status = "success"
        retrieval_error = None
        logger.info(
            "FalkorDB retrieval succeeded in %.2fs: found %d grounded memory records",
            retrieval_time,
            len(evidence),
        )
    else:
        retrieval_status = "no_matches"
        retrieval_error = None
        logger.info(
            "FalkorDB retrieval finished in %.2fs: 0 matching records in memory graph",
            retrieval_time,
        )

    if has_historical_evidence:
        evidence_text = "Retrieved Historical Memories (from FalkorDB):\n"
        for i, item in enumerate(evidence, start=1):
            evidence_text += (
                f"[{i}] Session: {item['session']}\n"
                f"    Error: {item['error']}\n"
                f"    Recorded Solution: {item['solution']}\n"
                f"    Recorded Date: {item['created_at']}\n"
            )
    else:
        evidence_text = (
            "Retrieved Historical Memories (from FalkorDB):\n"
            "[NONE FOUND IN GRAPH - State explicitly that no past team records exist for this issue]\n"
        )

    # Validate API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENROUTER_API_KEY is not configured in .env; skipping inference")
        return AgentResponse(
            success=False,
            evidence=evidence,
            has_historical_evidence=has_historical_evidence,
            model_used=model,
            error_type="auth_missing",
            error_message="OPENROUTER_API_KEY is not configured in .env. Please set it to enable the AI Agent.",
            retrieval_status=retrieval_status,
            retrieval_error=retrieval_error,
            retrieval_time_seconds=retrieval_time,
            inference_status="skipped",
            inference_error="Missing OPENROUTER_API_KEY",
            timeout_seconds=bounded_timeout,
        )

    # Step 2: Query the LLM via OpenRouter (single request, bounded timeout, no automatic infinite retries)
    logger.info(
        "Starting LLM inference with OpenRouter (model='%s', bounded_timeout=%.1fs)",
        model,
        bounded_timeout,
    )
    t_inf_start = time.time()
    try:
        answer = call_openrouter_api(
            user_prompt=cleaned_query,
            evidence_text=evidence_text,
            model=model,
            api_key=api_key,
            timeout=bounded_timeout,
        )
        inference_time = time.time() - t_inf_start
        logger.info("LLM inference succeeded in %.2fs", inference_time)
        return AgentResponse(
            success=True,
            answer=answer,
            evidence=evidence,
            has_historical_evidence=has_historical_evidence,
            model_used=model,
            timeout_seconds=bounded_timeout,
            retrieval_status=retrieval_status,
            retrieval_error=retrieval_error,
            retrieval_time_seconds=retrieval_time,
            inference_status="success",
            inference_time_seconds=inference_time,
        )
    except (requests.Timeout, TimeoutError) as exc:
        inference_time = time.time() - t_inf_start
        timeout_msg = sanitize_error_message(str(exc), api_key=api_key)
        logger.warning("LLM inference timed out after %.2fs", inference_time)
        return AgentResponse(
            success=False,
            answer="",
            evidence=evidence,
            has_historical_evidence=has_historical_evidence,
            model_used=model,
            error_type="timeout",
            error_message=timeout_msg,
            retrieval_status=retrieval_status,
            retrieval_error=retrieval_error,
            retrieval_time_seconds=retrieval_time,
            inference_status="timeout",
            inference_error=timeout_msg,
            inference_time_seconds=inference_time,
            timeout_seconds=bounded_timeout,
            is_timeout=True,
        )
    except Exception as exc:
        inference_time = time.time() - t_inf_start
        safe_err = sanitize_error_message(str(exc), api_key=api_key)
        logger.error("LLM inference failed in %.2fs: %s", inference_time, type(exc).__name__)
        return AgentResponse(
            success=False,
            answer="",
            evidence=evidence,
            has_historical_evidence=has_historical_evidence,
            model_used=model,
            error_type=type(exc).__name__,
            error_message=safe_err,
            retrieval_status=retrieval_status,
            retrieval_error=retrieval_error,
            retrieval_time_seconds=retrieval_time,
            inference_status="error",
            inference_error=safe_err,
            inference_time_seconds=inference_time,
            timeout_seconds=bounded_timeout,
            is_timeout=False,
        )
