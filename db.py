import os
from typing import Any, Dict
from dotenv import load_dotenv
from falkordb import FalkorDB
from falkordb.graph import Graph

# Load environment variables from .env
load_dotenv()

DEFAULT_GRAPH_NAME = "developer_memory"


def get_config_var(key: str, default: Any = None) -> Any:
    """
    Retrieve configuration with clear precedence:
    1. Streamlit Community Cloud secrets (st.secrets) if running in/with Streamlit.
    2. Environment variables (os.environ populated by .env or system).
    3. Provided default value.
    Gracefully handles missing Streamlit secrets or non-Streamlit environments.
    """
    try:
        import streamlit as st
        from streamlit.errors import StreamlitSecretNotFoundError

        try:
            if key in st.secrets:
                val = st.secrets[key]
                if val is not None:
                    return str(val)
        except (StreamlitSecretNotFoundError, FileNotFoundError, KeyError, AttributeError):
            pass
    except ImportError:
        pass

    return os.environ.get(key, default)


def get_connection_params() -> Dict[str, Any]:
    """
    Parse and validate FalkorDB connection parameters from secrets or environment variables.
    Properly interprets FALKORDB_TLS as a boolean flag.
    """
    host = get_config_var("FALKORDB_HOST", "localhost")
    port_raw = get_config_var("FALKORDB_PORT", "6379")
    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        port = 6379

    username = get_config_var("FALKORDB_USERNAME")
    password = get_config_var("FALKORDB_PASSWORD")

    tls_raw = get_config_var("FALKORDB_TLS", "false")
    ssl = str(tls_raw).strip().lower() in ("true", "1", "yes", "t")

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "ssl": ssl,
    }


def _create_db_client() -> FalkorDB:
    """Create a new FalkorDB client instance without querying on creation."""
    params = get_connection_params()
    return FalkorDB(**params)


# Process-level singleton client for non-Streamlit environments (CLI, scripts, tests)
_standalone_db: FalkorDB | None = None


# Streamlit-cached factory function
try:
    import streamlit as st

    @st.cache_resource
    def _cached_streamlit_db() -> FalkorDB:
        return _create_db_client()

except Exception:
    _cached_streamlit_db = None


def get_db() -> FalkorDB:
    """
    Get the FalkorDB client instance.
    Uses Streamlit's @st.cache_resource when running inside Streamlit,
    or a process-level singleton when running in standalone Python/CLI mode.
    Does not execute any database queries during retrieval.
    """
    global _standalone_db

    in_streamlit = False
    try:
        from streamlit.runtime import exists as runtime_exists
        in_streamlit = runtime_exists()
    except Exception:
        in_streamlit = False

    if in_streamlit and _cached_streamlit_db is not None:
        return _cached_streamlit_db()

    if _standalone_db is None:
        _standalone_db = _create_db_client()
    return _standalone_db


def get_graph(graph_name: str = DEFAULT_GRAPH_NAME) -> Graph:
    """
    Get a Graph handle for the specified graph identifier.
    Uses the cached FalkorDB connection.
    Does not issue any network queries until a query is executed.
    """
    client = get_db()
    return client.select_graph(graph_name)
