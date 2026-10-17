from db import get_graph

graph = get_graph("connection_test")

result = graph.query("RETURN 1 AS connection_status")
print(result.result_set)
