from db import get_graph

graph = get_graph("developer_memory")

query = """
MATCH (s:Session)-[:ENCOUNTERED]->(e:Error)
      -[:RESOLVED_BY]->(sol:Solution)
RETURN s.title, e.description, sol.description
"""

result = graph.query(query)

for row in result.result_set:
    print(f"Session: {row[0]}")
    print(f"Error: {row[1]}")
    print(f"Solution: {row[2]}")
