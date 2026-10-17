
from memory import save_memory

first = save_memory(
    "Python environment setup",
    "ensurepip unavailable when creating venv",
    "Install the matching Python venv package and recreate the environment",
)

second = save_memory(
    "FalkorDB connection setup",
    "Python application could not connect to the database",
    "Verify the cloud connection settings and credentials",
)

print("First memory:", first)
print("Second memory:", second)
print("Different IDs:", first["memory_id"] != second["memory_id"])
