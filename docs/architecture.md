# Architecture

This document describes the design of build-kg: how data flows through the pipeline, the graph ontology system, the database schema, and the key tradeoffs in parsing strategy.

## Pipeline Overview

build-kg transforms any topic into a structured knowledge graph through an 8-phase pipeline. Each phase produces an artifact that feeds the next.

```
Phase 0       Phase 0.5      Phase 1        Phase 2        Phase 3        Phase 4        Phase 5        Phase 6
INIT          ONTOLOGY       DISCOVER       CRAWL          CHUNK          LOAD           PARSE          VALIDATE
--------      --------       --------       --------       --------       --------       --------       --------
Set graph     Auto-gen       WebSearch      crawl.py       chunk.py       load.py        parse.py       Cypher
name, dirs    ontology       WebFetch       (Crawl4AI)     (Unstructured) (PostgreSQL)   (Claude Haiku 3.5)  queries
              or load
              from profile
              +----------+   +----------+   +----------+   +----------+   +-----------+  +-----------+
              | ontology |   | crawl_   |   | Markdown |   | JSON     |   | source_   |  | Apache    |
              | .yaml    |   | manifest |-->| files    |-->| chunks   |-->| document  |->| AGE       |
              +----------+   | .json    |   | per page |   | per file |   | source_   |  | Graph DB  |
                             +----------+                               | fragment  |  +-----------+
                                                                         +-----------+
```

### Phase 0: Initialize

Create a working directory and choose a graph name. Graph names follow these conventions:

- **Regulatory topics**: `reg_<country_code>_<domain>` (e.g., `reg_sg_fb` for Singapore food and beverage)
- **Generic topics**: `kg_<topic>` (e.g., `kg_k8s_net` for Kubernetes networking)

```bash
WORK_DIR="./pipelines/kg_k8s_net_20260218"
mkdir -p "$WORK_DIR/crawl_output" "$WORK_DIR/chunk_output"
```

### Phase 0.5: Ontology Generation

This phase determines the graph structure — what node types and edge types to create.

**For domain profiles with a built-in ontology** (e.g., `food-safety`, `financial-aml`, `data-privacy`), the ontology is loaded directly from the profile's YAML file. No generation is needed.

**For generic topics** (or profiles without an ontology section), the Claude Code skill auto-generates an ontology by analyzing the topic. The generated ontology includes:

- **Node types** with labels, descriptions, and properties (3-7 types recommended)
- **Edge types** with source/target node labels and descriptions
- **Root node** — the primary node type that maps 1:1 to source fragments
- **JSON schema** — the expected LLM output format

Example auto-generated ontology for "kubernetes networking":

```yaml
nodes:
  - label: Component
    description: "A Kubernetes networking component"
    properties: {name: string, type: string, description: string, layer: string}
  - label: Concept
    description: "A networking concept or protocol"
    properties: {name: string, description: string, category: string}
  - label: Configuration
    description: "A configuration option or setting"
    properties: {name: string, description: string, default_value: string, scope: string}
edges:
  - label: USES
    source: Component
    target: Concept
    description: "Component uses this concept"
  - label: CONFIGURES
    source: Configuration
    target: Component
    description: "Configuration applies to component"
  - label: DEPENDS_ON
    source: Component
    target: Component
    description: "Component depends on another"
root_node: Component
json_schema: |
  {
    "entities": [
      {"_label": "Component|Concept|Configuration", "name": "...", ...}
    ],
    "relationships": [
      {"_label": "USES|CONFIGURES|DEPENDS_ON", "_from_index": 0, "_to_index": 1}
    ]
  }
```

The ontology is saved to `<WORK_DIR>/ontology.yaml` and passed to subsequent phases via the `--ontology` flag.

### Phase 1: Discover Sources

Source discovery follows a **5-round methodology** designed to systematically map the knowledge landscape for a given topic:

| Round | Name | Method | Purpose |
|-------|------|--------|---------|
| 1 | Landscape Mapping | 8-15 parallel web searches | Identify authoritative sources and their official websites |
| 2 | Deep Source Discovery | Fetch main pages from each source | Find individual documents, standards, specifications |
| 3 | Sub-Domain Coverage Verification | Cross-reference against checklist | Identify gaps in topic coverage |
| 4 | Gap Filling | Targeted searches for uncovered areas | Fill coverage gaps; aim for 90%+ coverage |
| 5 | Secondary & International Sources | Search for supporting material | Add context, completeness, and references |

The output of Phase 1 is a **crawl manifest** (`crawl_manifest.json`) that lists every source to crawl, with metadata. See [manifest-format.md](manifest-format.md) for the full schema.

Sources are assigned priority tiers that determine crawl depth and page limits:

| Tier | Description | Depth | Max Pages | Delay |
|------|-------------|-------|-----------|-------|
| P1 | Primary authoritative sources | 3 | 100 | 1500ms |
| P2 | Secondary documentation and standards | 2 | 50 | 1500ms |
| P3 | Supporting guides, FAQs, tutorials | 1 | 25 | 2000ms |
| P4 | Reference material, community resources | 1 | 15 | 2000ms |

### Phase 2: Crawl

The crawler (`build-kg-crawl`) uses [Crawl4AI](https://github.com/unclecode/crawl4ai) with a headless Chromium browser. It performs breadth-first traversal within the same domain, respecting the configured depth, page limit, and delay.

Each crawled page is saved as a markdown file. An optional cleaning step (`clean.sh`) removes breadcrumb navigation artifacts that appear on some government websites.

### Phase 3: Chunk

The chunker (`build-kg-chunk`) uses the [Unstructured](https://github.com/Unstructured-IO/unstructured) library to split documents into semantically coherent fragments. Two strategies are available:

- **`by_title`** (recommended): Respects document structure (headings, sections). Starts a new chunk at each heading boundary while staying under the character limit.
- **`basic`**: Fills chunks to the maximum character limit without regard for document structure.

Each chunk is saved as a JSON file with metadata including source file path, chunk index, fingerprint (SHA-256 for deduplication), and chunk position (first/middle/last/only).

### Phase 4: Load to Database

The loader (`build-kg-load`) reads chunk JSON files and inserts them into two relational tables (`source_document` and `source_fragment`) in PostgreSQL. It matches each chunk file to its source entry in the crawl manifest by looking for the `source_name` in the file path.

Adjacent chunks are linked via `context_before` and `context_after` fields, giving the parser surrounding context when processing each fragment.

For generic topics, the `jurisdiction`, `authority`, and `doc_type` fields are nullable. Topic-specific metadata can be stored in the `metadata` JSONB column.

### Phase 5: Parse with LLM

The parser reads fragments from `source_fragment`, sends each to Claude Haiku 3.5 (or GPT-4o-mini if using OpenAI) with a structured prompt, and loads the result into the Apache AGE graph. Two parser variants are available:

- **Synchronous** (`build-kg-parse`): Calls the LLM API in real-time. Fast turnaround, standard pricing.
- **Batch** (`build-kg-parse-batch`): Uses the Batch API. 50% cheaper, but results take 1-24 hours.

The parser operates in one of two modes based on the ontology:

- **Ontology-driven mode**: When an ontology with `json_schema` is provided (via `--ontology` flag or from a domain profile), the parser uses it to generate prompts and create graph nodes/edges dynamically.
- **Legacy regulatory mode**: When no ontology is present, the parser uses the hardcoded Provision/Requirement/Constraint structure.

See the [Batch vs Sync Tradeoffs](#batch-vs-sync-tradeoffs) section below.

### Phase 6: Validate

Run Cypher queries against the completed graph to produce a report card. In ontology-driven mode, validation counts nodes per label from the ontology definition. In legacy mode, it counts Provision, Requirement, and Constraint nodes.

---

## Graph Ontology

build-kg supports two ontology modes: **ontology-driven** (generic) and **regulatory** (legacy).

### Ontology-Driven Mode (Generic)

When an ontology is provided (either auto-generated or from a domain profile), the graph structure is defined entirely by the ontology configuration. Node labels, edge labels, and properties are all dynamic.

The LLM outputs entities and relationships in a generic JSON format:

```json
{
  "entities": [
    {"_label": "Component", "name": "kube-proxy", "type": "proxy", "layer": "L4"},
    {"_label": "Concept", "name": "iptables", "category": "packet filtering"}
  ],
  "relationships": [
    {"_label": "USES", "_from_index": 0, "_to_index": 1}
  ]
}
```

Each entity becomes a graph vertex with the specified label and properties. Each relationship becomes a graph edge connecting the referenced entities.

### Regulatory Mode (Legacy / Domain Profiles)

The built-in regulatory profiles (`food-safety`, `financial-aml`, `data-privacy`) define an explicit ontology with three vertex labels and two edge labels:

```
Provision ──DERIVED_FROM──> Requirement ──HAS_CONSTRAINT──> Constraint
```

More precisely, the edges point from child to parent:

- A **Requirement** is `DERIVED_FROM` a **Provision** (the requirement was extracted from the provision text).
- A **Requirement** `HAS_CONSTRAINT` linking to a **Constraint** (the constraint makes the requirement testable).

A single Provision can have multiple Requirements, and each Requirement can have multiple Constraints.

#### Provision

A provision is a fragment of regulatory text from a specific source.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier: `{authority}_{provision_id}_{fragment_id_prefix}` |
| `provision_id` | string | Extracted regulatory ID (e.g., `B.01.008.2`, `21 CFR 101.61`) or `UNKNOWN` |
| `text` | string | The regulatory text (truncated to 500 characters) |
| `jurisdiction` | string | ISO-style jurisdiction code (e.g., `CA`, `SG`, `US`) |
| `authority` | string | Issuing regulatory body (e.g., `CFIA`, `SFA`, `FDA`) |
| `fragment_id` | string | UUID linking back to `source_fragment` table |
| `doc_id` | string | UUID linking back to `source_document` table |
| `created_at` | string | ISO 8601 timestamp |

#### Requirement

A requirement is a single regulatory obligation extracted from a provision.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier: `{provision_id}_req_{index}` |
| `requirement_type` | string | Domain-specific type (e.g., `labelling`, `consent`, `monitoring`) |
| `deontic_modality` | string | One of: `must`, `must_not`, `may`, `should`, `should_not` |
| `description` | string | Human-readable description of the obligation |
| `applies_to_scope` | string | What the requirement applies to (e.g., `label`, `data_controller`) |

#### Constraint

A constraint makes a requirement machine-testable.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier: `{requirement_id}_const_{index}` |
| `logic_type` | string | One of: `threshold`, `pattern`, `enumeration`, `boolean` |
| `target_signal` | string | What is being measured (e.g., `product.sodium`, `breach.notification_time`) |
| `operator` | string | Comparison operator: `<=`, `>=`, `==`, `!=`, `<`, `>` |
| `threshold` | number | Numeric threshold value (for `threshold` logic type) |
| `unit` | string | Unit of measurement (e.g., `mg`, `hours`, `%`) |
| `pattern` | string | Regex pattern (for `pattern` logic type) |
| `allowed_values` | list | Permitted values (for `enumeration` logic type) |

#### Example Graph Fragment

```
(Provision {
    provision_id: "B.01.008.2",
    authority: "CFIA",
    jurisdiction: "CA"
})
    <--[DERIVED_FROM]--
(Requirement {
    requirement_type: "labelling",
    deontic_modality: "must",
    description: "Sodium content must be declared on the nutrition facts table",
    applies_to_scope: "label"
})
    --[HAS_CONSTRAINT]-->
(Constraint {
    logic_type: "threshold",
    target_signal: "product.sodium",
    operator: "<=",
    threshold: 140,
    unit: "mg"
})
```

---

## Database Schema

The relational layer in PostgreSQL bridges the raw crawled content to the Apache AGE graph. Two tables serve as the source of truth for provenance.

### source_document

One row per crawled source document (webpage). Linked to entries in the crawl manifest.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `doc_id` | UUID (PK) | no | Auto-generated primary key |
| `jurisdiction` | TEXT | yes | Jurisdiction code (null for generic topics) |
| `authority` | TEXT | yes | Source organization name (null for generic topics) |
| `publisher` | TEXT | yes | Publishing organization |
| `doc_type` | TEXT | yes | Document type (null for generic topics) |
| `title` | TEXT | no | Document title |
| `canonical_citation` | TEXT | yes | Official citation reference |
| `url` | TEXT | no | Source URL |
| `language` | TEXT | no | Language code, default `en` |
| `filepath` | TEXT (UNIQUE) | no | Local file path, used for upsert deduplication |
| `metadata` | JSONB | yes | Arbitrary key-value metadata for generic topics |
| `retrieved_at` | TIMESTAMPTZ | no | When the document was crawled |
| `created_at` | TIMESTAMPTZ | no | Row creation time |
| `updated_at` | TIMESTAMPTZ | no | Last update time |

### source_fragment

One row per chunk of a source document. This is the table the parser reads from.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `fragment_id` | UUID (PK) | no | Auto-generated primary key |
| `doc_id` | UUID (FK) | no | Reference to parent source_document |
| `canonical_locator` | TEXT | yes | Section/chunk identifier |
| `excerpt` | TEXT | no | The actual text content of the chunk |
| `context_before` | TEXT | yes | Last 200 characters of the preceding chunk |
| `context_after` | TEXT | yes | First 200 characters of the following chunk |
| `source_url` | TEXT | yes | URL of the original source |
| `jurisdiction` | TEXT | yes | Inherited from source_document (null for generic) |
| `authority` | TEXT | yes | Inherited from source_document (null for generic) |
| `doc_type` | TEXT | yes | Inherited from source_document (null for generic) |
| `metadata` | JSONB | yes | Arbitrary key-value metadata |
| `created_at` | TIMESTAMPTZ | no | Row creation time |

### Indexes

```sql
CREATE INDEX idx_sf_doc_id ON source_fragment(doc_id);
CREATE INDEX idx_sf_jurisdiction ON source_fragment(jurisdiction);
CREATE INDEX idx_sf_authority ON source_fragment(authority);
```

---

## Ontology Configuration

The ontology system is defined in `src/build_kg/domain.py` using Pydantic models:

### OntologyConfig

```python
class NodeDef(BaseModel):
    label: str              # Vertex label (e.g., "Component", "Provision")
    description: str = ""   # Used in LLM prompt for guidance
    properties: Dict[str, str] = {}  # name -> type (string, number, boolean, list)

class EdgeDef(BaseModel):
    label: str              # Edge label (e.g., "USES", "DERIVED_FROM")
    source: str             # Source node label
    target: str             # Target node label
    description: str = ""   # Used in LLM prompt for guidance

class OntologyConfig(BaseModel):
    description: str = ""
    nodes: List[NodeDef] = []
    edges: List[EdgeDef] = []
    root_node: str = ""     # Primary node that maps 1:1 to source fragments
    json_schema: Optional[str] = None  # Expected LLM output JSON format
```

### How It's Used

1. **Graph schema setup** (`setup_graph.py`): Creates vertex labels for each node in the ontology, or falls back to `RegulatorySource`, `Provision`, `Requirement`, `Constraint`.

2. **Prompt generation** (`domain.py`): When `ontology.json_schema` is set, `build_prompt()` generates a prompt that describes each node type and edge type, and includes the JSON schema as the expected output format. When empty, the legacy regulatory prompt template is used.

3. **Graph loading** (`parse.py`, `parse_batch.py`): In ontology-driven mode, the parser creates vertices and edges dynamically from the LLM's JSON output. In legacy mode, the hardcoded Provision/Requirement/Constraint Cypher queries are used.

---

## Provision ID Extraction

For regulatory domains, extracting the correct provision ID (e.g., `B.01.008.2` or `21 CFR 101.61`) is critical for linking graph nodes to their authoritative source. build-kg uses a **two-stage strategy**:

### Stage 1: Regex Extraction (Free, Fast)

The `ProvisionIDExtractor` class tries multiple regex patterns in priority order:

1. **canonical_locator** from chunk metadata (highest confidence, 0.95)
2. **Authority-specific patterns** (confidence 0.85):
   - CFIA: `B.01.008`, `B.01.008.2`, `D.01`
   - US CFR: `21 CFR 101.61`, `101.61`
   - General: `Section 101.61`, `Chapter 27`, `Article 15.2`
3. **Generic patterns** (confidence 0.70): subsection numbers, parenthetical references, schedule references

Exclusion filters prevent false positives from years (2024), percentages (15%), and measurement values (100mg).

### Stage 2: LLM Fallback

If regex fails to extract an ID, the LLM prompt includes an instruction to extract the provision ID. The parser then selects the best ID:

1. If regex found an ID with confidence >= 0.70, use it.
2. Else if the LLM found a non-UNKNOWN ID, use the LLM result.
3. Else if regex found an ID with any confidence, use it (better than UNKNOWN).
4. Otherwise, set the provision ID to `UNKNOWN`.

For generic (non-regulatory) topics where provision IDs don't exist, the ID extraction is skipped entirely and auto-generated UUIDs are used instead.

---

## Domain Profile System

build-kg uses YAML domain profiles to parameterize the pipeline. Profiles configure the ontology, LLM prompt, ID extraction patterns, and source discovery templates.

### Profile Structure

A domain profile controls four aspects of the pipeline:

1. **Ontology Configuration** (`ontology`): Node types, edge types, root node, and JSON schema for the knowledge graph. When present, enables ontology-driven mode. When absent (as in the `default` profile), the Claude Code skill auto-generates an ontology.

2. **Parsing Configuration** (`parsing`): System message, requirement types, deontic modalities, target signal examples, and scope examples used in the LLM prompt.

3. **ID Extraction Patterns** (`id_patterns`): Regex patterns for extracting provision IDs from regulatory text, authority-specific priority ordering, and exclusion filters.

4. **Discovery Configuration** (`discovery`): Search templates, sub-domain checklists, and priority tiers used by the Claude Code skill during Phase 1 source discovery.

### Inheritance

Profiles can inherit from a base profile using `extends: default`. Fields in the child profile override the base via deep merge. This avoids repeating universal configuration in every domain profile.

### Resolution Order

When loading a profile by name:
1. If the name is a file path (ends in `.yaml`/`.yml`), load directly
2. Otherwise, look for `{name}.yaml` in `src/build_kg/domains/`

The active profile is determined by:
1. `--domain` CLI flag (highest priority)
2. `DOMAIN` environment variable
3. Default: `food-safety`

### Built-in Profiles

| Profile | Ontology | Description |
|---------|----------|-------------|
| `default` | None (auto-generated) | Generic profile for any topic |
| `food-safety` | Provision/Requirement/Constraint | CFIA, FDA, SFA food safety and labeling |
| `financial-aml` | Provision/Requirement/Constraint | Anti-money laundering, KYC, financial compliance |
| `data-privacy` | Provision/Requirement/Constraint | GDPR, CCPA, data protection regulations |

---

## Batch vs Sync Tradeoffs

| Factor | Sync Parser (`build-kg-parse`) | Batch Parser (`build-kg-parse-batch`) |
|--------|-------------------------------|--------------------------------------|
| **Cost** | ~$0.30 per 1,000 fragments | ~$0.15 per 1,000 fragments (50% cheaper) |
| **Latency** | Real-time (seconds per fragment) | 1-24 hours for the entire batch |
| **Use when** | <500 fragments, iterating quickly, debugging | >=500 fragments, cost-sensitive, overnight runs |
| **Rate limiting** | Controlled by `RATE_LIMIT_DELAY` (default 1s) | Handled by the provider |
| **Error handling** | Immediate feedback per fragment | Errors collected in output file |
| **Resumability** | Re-run with `--offset` to skip processed fragments | Resubmit failed items |

### Cost Estimate Formula

```
Estimated cost = (number_of_fragments * avg_tokens_per_fragment) / 1,000,000 * price_per_million_tokens
```

For Claude Haiku 3.5 (or GPT-4o-mini) with typical text (~500 input tokens + ~300 output tokens per fragment):
- **Sync**: ~$0.00030 per fragment
- **Batch**: ~$0.00015 per fragment

### Recommended Workflow

For a typical graph build with 1,000-5,000 fragments:

1. Run `build-kg-parse --test` to verify the pipeline with 5 fragments (cost: < $0.01).
2. If results look good, use `build-kg-parse-batch` for the full run.
3. Submit the batch before end of day; process results the next morning.

---

## Data Flow Diagram

```
ontology.yaml (or profile)
        |
        v
crawl_manifest.json
        |
        v
  [build-kg-crawl]  ------>  ./crawl_output/<source_name>/*.md
                                       |
                                       v
                              [build-kg-chunk]  ------>  ./chunk_output/<source_name>/*_chunk_N.json
                                                                  |
                                                                  v
                                                         [build-kg-load]  ------>  source_document (PostgreSQL)
                                                                                   source_fragment (PostgreSQL)
                                                                                          |
                                                                                          v
                                                                                 [build-kg-parse]  ------>  Apache AGE Graph
                                                                                 (--ontology flag)          - Dynamic node labels
                                                                                                            - Dynamic edge labels
                                                                                                            - Properties from ontology
```
