# build-kg

Open-source tool that turns any topic into a structured knowledge graph stored in Apache AGE (PostgreSQL). The agent designs the ontology, discovers sources, crawls, chunks, loads, and parses — fully automated.

## Project Structure

```
src/build_kg/          Main Python package
  config.py            Configuration from .env
  crawl.py             Web crawler (Crawl4AI)
  chunk.py             Document chunker (Unstructured)
  load.py              Database loader (PostgreSQL)
  parse.py             Sync LLM parser
  parse_batch.py       Batch LLM parser (50% cheaper)
  setup_graph.py       Apache AGE graph initialization
  verify.py            Setup verification
  domain.py            Domain profile system
  domains/             YAML domain profiles
db/                    Docker Compose for PostgreSQL + AGE
docs/                  Static HTML documentation
tests/                 Test suite (pytest)
kg_builds/             Working directory for graph builds (gitignored)
```

## Setup

```
make setup             # Creates venv, installs deps, starts DB, inits graph
cp .env.example .env   # Then set ANTHROPIC_API_KEY (or OPENAI_API_KEY)
make verify            # Confirm everything works
```

Always activate the venv before Python commands: `. venv/bin/activate && <command>`

## Environment Variables

Required: `DB_PASSWORD`, `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Model for parsing |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model for parsing (if openai) |
| `AGE_GRAPH_NAME` | `knowledge_graph` | Graph name in PostgreSQL |
| `DOMAIN` | `default` | Domain profile |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `buildkg` | Database name |
| `DB_USER` | `buildkg` | Database user |

## Build & Test

```
make test              # pytest tests/ -v
make lint              # ruff check src/ tests/
```

Tests run without a database. Integration tests skip automatically if the DB is unavailable.

## Code Style

- Linter: Ruff (line length 120, rules: E, F, I, W)
- Fix: `ruff check --fix src/ tests/`

## Building a Knowledge Graph

When the user asks to build a knowledge graph about a topic, follow this pipeline:

### Phase 0: Init
1. Sanitize topic to graph-safe name (lowercase, underscores): "kubernetes networking" becomes `kubernetes_networking`
2. `mkdir -p kg_builds/$GRAPH_NAME`
3. Set `AGE_GRAPH_NAME=$GRAPH_NAME` in `.env`
4. `python -m build_kg.setup_graph`

### Phase 0.5: Ontology
Design 3-6 node types (PascalCase) and 3-8 edge types (UPPER_SNAKE_CASE) for the topic. Save as `kg_builds/$GRAPH_NAME/ontology.yaml`:

```yaml
description: "Ontology description"
nodes:
  - label: "NodeType"
    description: "What this represents"
    properties:
      name: "string"
      category: "string"
edges:
  - label: "RELATIONSHIP"
    source: "SourceNode"
    target: "TargetNode"
    description: "What this means"
root_node: "PrimaryNodeType"
json_schema: |
  {
    "entities": [{"_label": "NodeType", "name": "...", "category": "..."}],
    "relationships": [{"_label": "RELATIONSHIP", "_from_index": 0, "_to_index": 1}]
  }
```

Then: `python -m build_kg.setup_graph --ontology kg_builds/$GRAPH_NAME/ontology.yaml`

### Phase 1: Discover
Search the web for 5-15 authoritative sources. Create `kg_builds/$GRAPH_NAME/manifest.json` with source metadata (url, title, authority, priority tier P1/P2, crawl depth/pages).

### Phase 2: Crawl
For each source: `build-kg-crawl --url "$URL" --output kg_builds/$GRAPH_NAME/crawled/$SOURCE_NAME --depth $DEPTH --pages $MAX_PAGES --delay $DELAY --format markdown`

### Phase 3: Chunk
`build-kg-chunk kg_builds/$GRAPH_NAME/crawled kg_builds/$GRAPH_NAME/chunks --strategy by_title --max-chars 1000`

### Phase 4: Load
`build-kg-load kg_builds/$GRAPH_NAME/chunks --manifest kg_builds/$GRAPH_NAME/manifest.json`

### Phase 5: Parse
- Under 500 fragments: `build-kg-parse --ontology kg_builds/$GRAPH_NAME/ontology.yaml`
- Over 500 fragments (batch, 50% cheaper):
  ```
  build-kg-parse-batch prepare --ontology kg_builds/$GRAPH_NAME/ontology.yaml --output kg_builds/$GRAPH_NAME/batch_requests.jsonl
  build-kg-parse-batch submit kg_builds/$GRAPH_NAME/batch_requests.jsonl
  build-kg-parse-batch status $BATCH_ID --watch
  build-kg-parse-batch process $BATCH_ID --ontology kg_builds/$GRAPH_NAME/ontology.yaml
  ```

### Phase 6: Report
Query the graph with Cypher and present node/edge counts by type, example subgraphs, and cost estimate.

## CLI Entry Points

All commands require the venv to be activated.

| Command | Purpose |
|---|---|
| `build-kg-crawl` | Crawl a URL (Crawl4AI) |
| `build-kg-chunk` | Chunk documents (Unstructured) |
| `build-kg-load` | Load chunks to PostgreSQL |
| `build-kg-parse` | Parse fragments with LLM (sync) |
| `build-kg-parse-batch` | Parse fragments with Batch API |
| `build-kg-setup` | Initialize AGE graph schema |
| `build-kg-verify` | Verify system readiness |
| `build-kg-domains` | List available domain profiles |
