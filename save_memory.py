
import os
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

db = FalkorDB(
    host=os.environ["FALKORDB_HOST"],
    port=int(os.environ["FALKORDB_PORT"]),
    username=os.environ["FALKORDB_USERNAME"],
    password=os.environ["FALKORDB_PASSWORD"],
    ssl=False,
)

graph = db.select_graph("developer_memory")

query = """
MERGE (s:Session {id: 'session-001'})
SET s.title = 'WSL Python environment setup'

MERGE (e:Error {id: 'error-001'})
SET e.description = 'ensurepip unavailable when creating venv'

MERGE (sol:Solution {id: 'solution-001'})
SET sol.description = 'Install python3.14-venv and recreate the virtual environment'

MERGE (s)-[:ENCOUNTERED]->(e)
MERGE (e)-[:RESOLVED_BY]->(sol)

RETURN s.id, e.id, sol.id
"""

result = graph.query(query)
print(result.result_set)

