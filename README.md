# Developer Memory Graph

**Persistent developer memory for AI-assisted debugging, powered by FalkorDB and OpenRouter.**

Developer Memory Graph is a Streamlit application that stores development sessions, errors, and solutions in a graph database. When a developer encounters an issue, the AI agent searches historical team memories before generating troubleshooting recommendations.

## The Problem

Developers repeatedly encounter similar errors but often lose the context and solutions from previous debugging sessions. General-purpose AI assistants may provide useful advice without knowing what previously worked for a particular team.

Developer Memory Graph aims to preserve this experience as reusable, connected knowledge.

## How It Works

1. **Capture:** Store development sessions, errors, and solutions.
2. **Connect:** Represent historical knowledge through relationships in FalkorDB.
3. **Retrieve:** Search the graph for relevant historical debugging evidence.
4. **Reason:** Use an LLM to synthesize troubleshooting recommendations using the retrieved context.
5. **Verify:** Let the developer confirm whether a solution worked before recording it as verified knowledge.

## Features

- AI Developer Memory Agent
- Persistent graph-based storage with FalkorDB
- Retrieval of historical debugging sessions and solutions
- Search Memories interface
- Memory Graph visualization
- Save a Memory workflow
- OpenRouter-based LLM integration
- Separate reporting of retrieval and inference status
- Request timeout handling and error reporting

## Technology Stack

- Python
- Streamlit
- FalkorDB Cloud
- FalkorDB Python client
- OpenRouter API
- Requests
- python-dotenv
- streamlit-agraph for graph visualization

## Architecture

\\	ext
Developer Question
        |
        v
FalkorDB Memory Retrieval
        |
        v
Relevant Historical Evidence
        |
        v
OpenRouter LLM
        |
        v
Troubleshooting Recommendations
        |
        v
Developer Verification
        |
        v
Reusable Graph Memory
\
The agent distinguishes retrieved historical evidence from newly generated recommendations. Historical evidence should be interpreted as recorded experience, not an automatic guarantee that a solution will work in every environment.

## Getting Started

### Prerequisites

- Python 3.11 or later, subject to dependency compatibility
- A FalkorDB instance, such as FalkorDB Cloud
- An OpenRouter API key
- Git

### 1. Clone the repository

\\ash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd developer-memory-graph
\
### 2. Create and activate a virtual environment

On Linux or WSL:

\\ash
python3 -m venv .venv
source .venv/bin/activate
\
If creating the virtual environment fails because \ensurepip\ is unavailable on Ubuntu, install the appropriate \python3-venv\ package for your Python version and recreate the environment.

### 3. Install dependencies

\\ash
pip install -r requirements.txt
\
### 4. Configure environment variables

\\ash
cp .env.example .env
\
Edit \.env\ with your own FalkorDB connection details and OpenRouter API key.

Required configuration:

| Variable | Description |
|---|---|
| \FALKORDB_HOST\ | FalkorDB host |
| \FALKORDB_PORT\ | FalkorDB port |
| \FALKORDB_USERNAME\ | FalkorDB username |
| \FALKORDB_PASSWORD\ | FalkorDB password |
| \FALKORDB_TLS\ | Whether TLS is enabled for the connection |
| \OPENROUTER_API_KEY\ | OpenRouter API key |
| \OPENROUTER_MODEL\ | OpenRouter model identifier |
| \OPENROUTER_TIMEOUT\ | Optional request timeout in seconds |

Never commit \.env\ or publish credentials in screenshots, logs, or documentation.

### 5. Run the application

\\ash
streamlit run app.py
\
## Application Tabs

- **AI Memory Agent:** Ask debugging questions and inspect retrieved evidence.
- **Save a Memory:** Record development sessions, errors, and solutions.
- **Search Memories:** Search stored development knowledge.
- **Memory Graph:** Explore connected sessions, errors, and solutions.

## Testing

The project includes unit tests for agent timeout and error handling.

Run:

\\ash
python -m unittest test_timeout_handling.py -v
\
Avoid running tests that write to a shared or production FalkorDB instance unless you understand their effects and are using a safe test database.

## Current Status

The application has demonstrated historical memory retrieval and AI-generated troubleshooting for Python virtual-environment and Git push-rejection scenarios.

Model latency and free-tier availability may vary. Review generated recommendations before applying commands to important repositories or systems.

## Hackathon

Built for the **WeMakeDevs × FalkorDB Graph Hacks: Context for AI Agents** hackathon, under the Agent Memory and Coordination track.

## License

A license has not yet been selected. Add a license before presenting this repository as open source.
