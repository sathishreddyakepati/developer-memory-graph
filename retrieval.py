from db import get_db, get_graph


def search_memories(keyword):
    """Search developer memories by matching keyword in session, error, or solution."""
    graph = get_graph()
    query = """
    MATCH (s:Session)-[:ENCOUNTERED]->(e:Error)
          -[:RESOLVED_BY]->(sol:Solution)
    WITH s, e, sol,
         CASE
             WHEN toLower(e.description) CONTAINS toLower($keyword)
                 THEN 3
             ELSE 0
         END
         +
         CASE
             WHEN toLower(s.title) CONTAINS toLower($keyword)
                 THEN 2
             ELSE 0
         END
         +
         CASE
             WHEN toLower(sol.description) CONTAINS toLower($keyword)
                 THEN 1
             ELSE 0
         END AS relevance
    WHERE relevance > 0
    RETURN s.title, e.description, sol.description,
           s.created_at, relevance
    ORDER BY relevance DESC, s.created_at DESC
    LIMIT 10
    """
    result = graph.query(query, {"keyword": keyword})
    return result.result_set


def get_graph_data():
    """Retrieve recent paths for graph visualization in Streamlit."""
    graph = get_graph()
    query = """
    MATCH (s:Session)-[:ENCOUNTERED]->(e:Error)
          -[:RESOLVED_BY]->(sol:Solution)
    RETURN s.id, s.title, e.id, e.description,
           sol.id, sol.description
    ORDER BY s.created_at DESC
    LIMIT 30
    """
    result = graph.query(query)
    return result.result_set


def get_graph_stats():
    """
    Count sessions, errors, solutions, and relationships.
    Uses OPTIONAL MATCH so counts safely return 0 when entities or edges are missing.
    """
    graph = get_graph()
    query = """
    OPTIONAL MATCH (s:Session)
    WITH count(s) AS sessions
    OPTIONAL MATCH (e:Error)
    WITH sessions, count(e) AS errors
    OPTIONAL MATCH (sol:Solution)
    WITH sessions, errors, count(sol) AS solutions
    OPTIONAL MATCH ()-[r]->()
    RETURN sessions, errors, solutions, count(r) AS relationships
    """
    result = graph.query(query)
    if not result or not result.result_set:
        return [0, 0, 0, 0]
    return result.result_set[0]


def __getattr__(name):
    """Provide lazy attribute access for backwards compatibility."""
    if name == "graph":
        return get_graph()
    if name == "db":
        return get_db()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


if __name__ == "__main__":
    keyword = input("What do you want to remember? ").strip()

    if not keyword:
        print("Please enter a search term.")
    else:
        memories = search_memories(keyword)

        if not memories:
            print("No matching memories found.")
        else:
            for index, row in enumerate(memories, start=1):
                print(f"\nMemory {index}")
                print(f"Session: {row[0]}")
                print(f"Error: {row[1]}")
                print(f"Solution: {row[2]}")
                print(f"Created: {row[3]}")
