# CLI Reference: Parsers

build-kg provides two parsers for converting text fragments into Apache AGE graph nodes. Both support two modes: **ontology-driven** (generic, any topic) and **regulatory** (legacy, Provision/Requirement/Constraint). Both produce the same quality of graph output but differ in cost, latency, and workflow.

---

## Sync Parser: build-kg-parse

Real-time parsing using the OpenAI Chat Completions API. Each fragment is sent to GPT-4o-mini individually, and the result is loaded into the graph immediately.

### Usage

```bash
build-kg-parse [OPTIONS]
```

Or via Python module:

```bash
python -m build_kg.parse [OPTIONS]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | all | Maximum number of fragments to process |
| `--offset N` | `0` | Skip the first N fragments |
| `--jurisdiction CODE` | all | Filter by jurisdiction code (e.g., `SG`, `CA`, `US`) |
| `--test` | off | Test mode: process only 5 fragments |
| `--domain NAME` | `food-safety` | Domain profile name or path to custom YAML profile |
| `--ontology PATH` | none | Path to an ontology YAML file (enables ontology-driven mode) |

### Environment Variables

The parser reads these from `.env` or the environment:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGE_GRAPH_NAME` | `reg_ca` | Apache AGE graph to load results into |
| `OPENAI_API_KEY` | **(required)** | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model to use for parsing |
| `BATCH_SIZE` | `10` | Number of fragments per internal batch (for progress reporting) |
| `MAX_WORKERS` | `3` | Concurrent worker count (currently sequential) |
| `RATE_LIMIT_DELAY` | `1.0` | Seconds to wait between API calls |
| `DOMAIN` | `food-safety` | Domain profile name or path (overridden by `--domain` flag) |

### Parsing Modes

#### Ontology-Driven Mode

When `--ontology` is provided or the active domain profile has an ontology with `json_schema`, the parser uses the ontology to:

1. Generate prompts that describe node types, edge types, and expected properties
2. Parse the LLM's JSON output into entities and relationships
3. Create graph vertices and edges dynamically based on the ontology labels

The LLM is expected to return JSON in this format:

```json
{
  "entities": [
    {"_label": "Component", "name": "kube-proxy", "type": "proxy"},
    {"_label": "Concept", "name": "iptables", "category": "packet filtering"}
  ],
  "relationships": [
    {"_label": "USES", "_from_index": 0, "_to_index": 1}
  ]
}
```

#### Regulatory Mode (Legacy)

When no ontology is provided and the domain profile doesn't have one, the parser uses the hardcoded Provision/Requirement/Constraint structure. This is the original regulatory parsing mode.

### Examples

#### Test with 5 fragments (regulatory)

```bash
build-kg-parse --test
```

#### Parse with a custom ontology (generic topic)

```bash
AGE_GRAPH_NAME=kg_k8s_net build-kg-parse --ontology ./ontology.yaml --limit 100
```

#### Parse 100 fragments for Singapore (regulatory)

```bash
AGE_GRAPH_NAME=reg_sg_fb build-kg-parse --domain food-safety --limit 100 --jurisdiction SG
```

#### Parse with a different domain profile

```bash
build-kg-parse --domain financial-aml --jurisdiction US
```

#### Parse all fragments, skip first 500

```bash
build-kg-parse --offset 500
```

### When to Use

- **<500 fragments**: The sync parser is convenient for small to medium runs.
- **Debugging**: Immediate feedback makes it easy to inspect results and iterate.
- **Interactive development**: When you want to see results as they are produced.

### ID Extraction (Regulatory Mode Only)

The sync parser includes a two-stage ID extraction pipeline for regulatory domains:

1. **Regex extraction** (free, instant): Tries authority-specific patterns (CFIA B.01.008, US CFR 21 CFR 101.61, Section/Chapter/Article references) against the fragment text and canonical_locator metadata.
2. **LLM extraction** (paid, via the parsing prompt): The GPT-4o-mini prompt asks for the provision ID as part of the structured output.

The parser chooses the best ID source:
- Regex with confidence >= 0.70: Use regex result
- Regex failed but LLM found an ID: Use LLM result
- Regex with any confidence and LLM failed: Use regex result
- Both failed: Set provision_id to `UNKNOWN`

In ontology-driven mode, ID extraction is skipped and auto-generated IDs are used.

---

## Batch Parser: build-kg-parse-batch

Uses the OpenAI Batch API for 50% cheaper processing. Designed for large-scale runs (>=500 fragments). The workflow has four subcommands that are run sequentially.

### Usage

```bash
build-kg-parse-batch <command> [OPTIONS]
```

Or via Python module:

```bash
python -m build_kg.parse_batch <command> [OPTIONS]
```

### Subcommands

#### `prepare` -- Create a JSONL Batch File

Fetches fragments from the database and writes them as OpenAI Batch API requests in JSONL format.

```bash
build-kg-parse-batch prepare [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | all | Maximum number of fragments to include |
| `--offset N` | `0` | Skip the first N fragments |
| `--jurisdiction CODE` | all | Filter by jurisdiction code |
| `--output FILENAME` | `batch_requests.jsonl` | Output JSONL filename (saved in `./batch_data/`) |
| `--domain NAME` | `food-safety` | Domain profile name or path |
| `--ontology PATH` | none | Path to ontology YAML file |

Example:

```bash
build-kg-parse-batch prepare --jurisdiction SG --output sg_batch.jsonl
```

Example (generic topic with ontology):

```bash
build-kg-parse-batch prepare --ontology ./ontology.yaml --output k8s_batch.jsonl
```

Output files:
- `batch_data/sg_batch.jsonl` -- The JSONL file to submit to OpenAI
- `batch_data/sg_batch.jsonl.metadata.json` -- Fragment metadata for processing results later

#### `submit` -- Submit Batch to OpenAI

Uploads the JSONL file and creates a batch job.

```bash
build-kg-parse-batch submit <batch_file>
```

| Argument | Description |
|----------|-------------|
| `batch_file` | Path to the JSONL file created by `prepare` |

Example:

```bash
build-kg-parse-batch submit batch_data/sg_batch.jsonl
```

Output:
- Prints the batch ID (e.g., `batch_abc123def456`)
- Saves batch info to `batch_data/batch_<batch_id>.info.json`

#### `status` -- Check Batch Status

Checks the current status of a submitted batch.

```bash
build-kg-parse-batch status <batch_id> [OPTIONS]
```

| Argument/Flag | Description |
|---------------|-------------|
| `batch_id` | The OpenAI batch ID from the `submit` step |
| `--watch` | Poll every 60 seconds until the batch completes |

Example (one-shot):

```bash
build-kg-parse-batch status batch_abc123def456
```

Example (watch mode):

```bash
build-kg-parse-batch status batch_abc123def456 --watch
```

Possible statuses:
- `validating` -- OpenAI is validating the input file
- `in_progress` -- Requests are being processed
- `completed` -- All requests finished
- `failed` -- The batch failed (check errors)
- `expired` -- The batch expired (24-hour window exceeded)
- `cancelled` -- The batch was cancelled

#### `process` -- Download Results and Load to Graph

Downloads the completed batch results and loads each parsed entity into the Apache AGE graph.

```bash
build-kg-parse-batch process <batch_id> [OPTIONS]
```

| Argument/Flag | Description |
|---------------|-------------|
| `batch_id` | The OpenAI batch ID from the `submit` step |
| `--ontology PATH` | Path to ontology YAML file (must match the one used in `prepare`) |

Example (regulatory):

```bash
AGE_GRAPH_NAME=reg_sg_fb build-kg-parse-batch process batch_abc123def456
```

Example (generic with ontology):

```bash
AGE_GRAPH_NAME=kg_k8s_net build-kg-parse-batch process batch_abc123def456 --ontology ./ontology.yaml
```

Output files:
- `batch_data/batch_<batch_id>_results.jsonl` -- Downloaded results
- `batch_data/batch_<batch_id>_errors.jsonl` -- Downloaded errors (if any)

### Full Batch Workflow

#### Regulatory topic

```bash
# Step 1: Prepare
build-kg-parse-batch prepare --jurisdiction SG

# Step 2: Submit
build-kg-parse-batch submit batch_data/batch_requests.jsonl

# Step 3: Wait and monitor
build-kg-parse-batch status batch_abc123def456 --watch

# Step 4: Process results into graph
AGE_GRAPH_NAME=reg_sg_fb build-kg-parse-batch process batch_abc123def456
```

#### Generic topic

```bash
# Step 1: Prepare with ontology
build-kg-parse-batch prepare --ontology ./ontology.yaml

# Step 2: Submit
build-kg-parse-batch submit batch_data/batch_requests.jsonl

# Step 3: Wait and monitor
build-kg-parse-batch status batch_abc123def456 --watch

# Step 4: Process results with same ontology
AGE_GRAPH_NAME=kg_k8s_net build-kg-parse-batch process batch_abc123def456 --ontology ./ontology.yaml
```

### When to Use

- **>=500 fragments**: The 50% cost savings become significant.
- **Overnight runs**: Submit before end of day, process results the next morning.
- **Budget-sensitive projects**: When minimizing API costs matters.

### Batch Data Directory

All batch files are stored in `./batch_data/` relative to the current working directory:

```
batch_data/
  batch_requests.jsonl                    # Prepared requests
  batch_requests.jsonl.metadata.json      # Fragment metadata
  batch_batch_abc123def456.info.json      # Submission info
  batch_batch_abc123def456_results.jsonl  # Downloaded results
  batch_batch_abc123def456_errors.jsonl   # Downloaded errors
```

---

## Cost Comparison

| Parser | Pricing Model | Cost per 1,000 Fragments | Best For |
|--------|--------------|--------------------------|----------|
| `build-kg-parse` (sync) | Standard OpenAI API | ~$0.30 | Small runs (<500), debugging, interactive use |
| `build-kg-parse-batch` (batch) | OpenAI Batch API (50% discount) | ~$0.15 | Large runs (>=500), overnight processing |

Cost estimates assume GPT-4o-mini with an average of ~500 input tokens and ~300 output tokens per fragment.

### Cost Examples

| Fragments | Sync Cost | Batch Cost | Savings |
|-----------|-----------|------------|---------|
| 100 | ~$0.03 | ~$0.015 | $0.015 |
| 1,000 | ~$0.30 | ~$0.15 | $0.15 |
| 5,000 | ~$1.50 | ~$0.75 | $0.75 |
| 10,000 | ~$3.00 | ~$1.50 | $1.50 |

---

## Graph Output

Both parsers support two output modes depending on whether an ontology is provided.

### Ontology-Driven Mode (Generic)

- **Nodes Created**: Dynamic, based on ontology definition. Each entity type (e.g., Component, Concept, Configuration) becomes a vertex label.
- **Edges Created**: Dynamic, based on ontology definition (e.g., USES, CONFIGURES, DEPENDS_ON).
- **Properties**: Dynamic, from the LLM output matching the ontology's property definitions.

### Regulatory Mode (Legacy)

- **Provision**: One per fragment that has extractable requirements
- **Requirement**: One per regulatory obligation found in the fragment
- **Constraint**: One per testable condition on a requirement
- **DERIVED_FROM**: Links a Requirement to its parent Provision
- **HAS_CONSTRAINT**: Links a Requirement to its Constraint(s)

### Skipped Fragments

Fragments are skipped (not loaded to graph) when:
- The LLM returns empty entities/requirements (the text contains no extractable knowledge)
- The LLM response is not valid JSON
- A graph insertion error occurs (the fragment is counted as failed)

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "OpenAI API error 401" | Check `OPENAI_API_KEY` in `.env` |
| "No fragments found" | Verify that `build-kg-load` ran successfully; check `source_fragment` table |
| "Graph loading failed" | Check that the graph exists: `build-kg-setup` |
| Batch still in "validating" status | Wait -- OpenAI batches take 1-24 hours |
| Batch status "failed" | Check the error output; common cause is malformed JSONL |
| Batch status "expired" | The 24-hour window elapsed; resubmit the batch |
| "Metadata file not found" during process | Ensure you run `process` from the same directory where you ran `prepare` |
| High number of UNKNOWN provision IDs | Expected for jurisdictions without structured IDs; consider post-processing |
| "Ontology file not found" | Check that the `--ontology` path is correct and the file exists |
