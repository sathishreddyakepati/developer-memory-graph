import uuid
from datetime import datetime, timezone
from db import get_db, get_graph


def save_memory(session_title, error_description, solution_description, status="recorded"):
    """
    Save a new development experience (session, error, and solution)
    to FalkorDB using the centralized connection.
    Status defaults to safe 'recorded' unless explicitly marked 'verified'.
    """
    memory_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    graph = get_graph()

    query = """
    CREATE (s:Session {
        id: $session_id,
        memory_id: $memory_id,
        title: $session_title,
        created_at: $created_at
    })
    CREATE (e:Error {
        id: $error_id,
        memory_id: $memory_id,
        description: $error_description
    })
    CREATE (sol:Solution {
        id: $solution_id,
        memory_id: $memory_id,
        description: $solution_description,
        status: $status
    })
    CREATE (s)-[:ENCOUNTERED]->(e)
    CREATE (e)-[:RESOLVED_BY]->(sol)
    RETURN $memory_id AS memory_id
    """

    params = {
        "memory_id": memory_id,
        "session_id": f"session-{memory_id}",
        "session_title": session_title,
        "error_id": f"error-{memory_id}",
        "error_description": error_description,
        "solution_id": f"solution-{memory_id}",
        "solution_description": solution_description,
        "status": status,
        "created_at": created_at,
    }

    result = graph.query(query, params)
    saved_id = result.result_set[0][0]

    return {
        "memory_id": saved_id,
        "session": session_title,
        "error": error_description,
        "solution": solution_description,
        "status": status,
        "created_at": created_at,
    }


def __getattr__(name):
    """Provide lazy attribute access for backwards compatibility."""
    if name == "graph":
        return get_graph()
    if name == "db":
        return get_db()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
