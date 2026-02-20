# Quickstart Tutorial

Get from zero to a working knowledge graph in 5 minutes. This tutorial crawls a small public website, chunks the content, loads it into PostgreSQL, and parses it into an Apache AGE graph.

## Prerequisites

Before you begin, make sure you have:

- **Python 3.10+** (`python3 --version`)
- **Docker** (`docker --version`)
- **An OpenAI API key** (get one at [platform.openai.com](https://platform.openai.com))

## Step 1: Clone and Install

```bash
git clone https://github.com/agtm1199/build-kg.git
cd build-kg

# Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Install Chromium for the web crawler
crawl4ai-setup
```

Expected output (last few lines):

```
Successfully installed build-kg-0.3.0
[crawl4ai] Chromium installed successfully
```

## Step 2: Start the Database

```bash
docker compose -f db/docker-compose.yml up -d
```

Wait a few seconds for PostgreSQL to initialize. Check that it is running:

```bash
docker compose -f db/docker-compose.yml ps
```

Expected output:

```
NAME           IMAGE        ...   STATUS                    PORTS
build-kg-db    apache/age   ...   Up 5 seconds (healthy)    0.0.0.0:5432->5432/tcp
```

## Step 3: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set your OpenAI API key:

```
OPENAI_API_KEY=sk-your-actual-key-here
```

The database credentials in `.env.example` already match the Docker container defaults, so no other changes are needed.

## Step 4: Initialize the Graph

```bash
python -m build_kg.setup_graph
```

Expected output:

```
======================================================================
Apache AGE Graph Setup
======================================================================
Checking for Apache AGE extension...
  Apache AGE extension already installed
  AGE loaded into search path

Checking for graph 'reg_ca'...
Creating graph 'reg_ca'...
  Graph 'reg_ca' created successfully

Creating graph schema...
  Graph schema initialized

Vertex labels created:
  - RegulatorySource
  - Provision
  - Requirement
  - Constraint

======================================================================
  Setup completed successfully!
Graph 'reg_ca' is ready for use
======================================================================
```

To create a graph with a custom ontology (for generic topics):

```bash
AGE_GRAPH_NAME=kg_k8s_net python -m build_kg.setup_graph --ontology ./ontology.yaml
```

This creates vertex labels from the ontology definition instead of the default regulatory labels.

## Step 5: Verify Setup

```bash
python -m build_kg.verify
```

Expected output:

```
======================================================================
Setup Verification
======================================================================
1. Verifying database connection...
     Connected to PostgreSQL
     Version: PostgreSQL 16.x
2. Verifying Apache AGE extension...
     AGE extension installed (version 1.5.0)
     Graph 'reg_ca' exists
3. Verifying source data...
     Found 0 fragments with excerpts
     Found 0 source documents
4. Verifying OpenAI API access...
     OpenAI API connection successful
     Model: gpt-4o-mini
======================================================================
  All checks passed! System is ready.
======================================================================
```

## Step 6: Crawl a Small Website

For this tutorial, we will crawl 3 pages from a public website. Replace the URL below with any public page you want to index.

```bash
mkdir -p tutorial/crawl_output tutorial/chunk_output

build-kg-crawl \
  --url "https://www.canada.ca/en/health-canada/services/food-nutrition/food-labelling.html" \
  --depth 1 \
  --pages 3 \
  --delay 2000 \
  --format markdown \
  --output ./tutorial/crawl_output/hc_labelling/
```

Expected output:

```
Web Crawler Started

Configuration:
  Start URL:      https://www.canada.ca/en/health-canada/services/food-nutrition/food-labelling.html
  Delay:          2000ms
  Output Format:  markdown
  Max Pages:      3
  Max Depth:      1
  Output Dir:     /path/to/build-kg/tutorial/crawl_output/hc_labelling

Starting crawl...

[1/3] Crawling (depth 0): https://www.canada.ca/.../food-labelling.html
  Status: 200
  Saved: food-labelling_depth0_20260218_143022.md

[2/3] Crawling (depth 1): https://www.canada.ca/.../nutrition-labelling.html
  Status: 200
  Saved: nutrition-labelling_depth1_20260218_143025.md

[3/3] Crawling (depth 1): https://www.canada.ca/.../ingredient-list.html
  Status: 200
  Saved: ingredient-list_depth1_20260218_143028.md

Crawling Complete!

Summary:
  Pages Crawled:  3
  Output Files:   3
  Output Dir:     /path/to/build-kg/tutorial/crawl_output/hc_labelling
```

**Cost: Free.** Crawling uses no API calls.

## Step 7: Chunk the Output

```bash
build-kg-chunk \
  ./tutorial/crawl_output/ \
  ./tutorial/chunk_output/ \
  --strategy by_title \
  --max-chars 1000
```

Expected output (abbreviated):

```
================================================================================
DOCUMENT CHUNKER - Powered by Unstructured
================================================================================

  PROCESSING FILE
  File: hc_labelling/food-labelling_depth0_20260218_143022.md
  Type: .MD
  Strategy: by_title

  [STEP 1/4] Extracted 24 elements in 45ms
  [STEP 2/4] Generated 8 chunks in 12ms
  [STEP 3/4] Output directory ready
  [STEP 4/4] Saved all chunks in 5ms

  COMPLETED SUCCESSFULLY
  Total chunks: 8

...

PROCESSING SUMMARY
All files processed successfully!

  Total files: 3
  Successful: 3
  Failed: 0
  Total time: 0.23s
```

**Cost: Free.** Chunking runs entirely locally.

## Step 8: Load to Database

First, create a minimal crawl manifest for our tutorial data:

```bash
cat > tutorial/crawl_manifest.json << 'EOF'
{
  "topic": "Canadian food labelling",
  "graph_name": "reg_ca",
  "created_at": "2026-02-18T14:30:00Z",
  "sources": [
    {
      "source_name": "hc_labelling",
      "url": "https://www.canada.ca/en/health-canada/services/food-nutrition/food-labelling.html",
      "title": "Health Canada Food Labelling",
      "authority": "Health Canada",
      "jurisdiction": "CA",
      "doc_type": "guidance",
      "priority": "P1"
    }
  ],
  "defaults": {
    "jurisdiction": "CA",
    "authority": "Health Canada",
    "doc_type": "guidance"
  }
}
EOF
```

Now load the chunks:

```bash
build-kg-load ./tutorial/chunk_output/ --manifest ./tutorial/crawl_manifest.json
```

Expected output:

```
============================================================
  Chunk-to-Database Loader
============================================================
  Manifest: tutorial/crawl_manifest.json
  Sources:  1
  Defaults: jurisdiction=CA, authority=Health Canada

Scanning chunk files...
  Found 22 chunks across 3 documents

Processing: food-labelling_depth0_20260218_143022 (8 chunks)
  Document: a1b2c3d4... (Health Canada, CA)
  Fragments: 8 inserted

Processing: nutrition-labelling_depth1_20260218_143025 (7 chunks)
  Document: e5f6g7h8... (Health Canada, CA)
  Fragments: 7 inserted

Processing: ingredient-list_depth1_20260218_143028 (7 chunks)
  Document: i9j0k1l2... (Health Canada, CA)
  Fragments: 7 inserted

============================================================
  LOAD COMPLETE
============================================================
  Documents inserted:  3
  Documents skipped:   0
  Fragments inserted:  22
  Errors:              0
============================================================
```

## Step 9: Parse with LLM

Run the parser in test mode first (5 fragments only):

```bash
build-kg-parse --test
```

Then parse a small batch (10 fragments):

```bash
build-kg-parse --limit 10
```

Expected output (abbreviated):

```
======================================================================
Knowledge Graph Parser
======================================================================
Graph: reg_ca
Model: gpt-4o-mini
Batch size: 10
======================================================================

Fetching fragments (limit=10, offset=0, jurisdiction=None)...
Found 10 fragments to process

======================================================================
Batch 1/1
======================================================================

Processing fragment a1b2c3d4...
  Regex extracted ID: B.01.008 (confidence: 0.85, method: regex)
  Using regex ID: B.01.008
  Extracted 2 requirements
  Loaded to graph

Processing fragment e5f6g7h8...
  No ID extracted from regex or LLM
  Extracted 1 requirements
  Loaded to graph

...

======================================================================
SUMMARY
======================================================================
Total processed:  10
  Success:        8
  Failed:         0
  Skipped:        2

ID Extraction Methods:
  Regex:          5
  LLM:            3

Duration:         15.2 seconds
Avg per fragment: 1.52 seconds
======================================================================
```

For **generic topics** with a custom ontology, pass the `--ontology` flag:

```bash
AGE_GRAPH_NAME=kg_k8s_net build-kg-parse --ontology ./ontology.yaml --limit 10
```

**Cost: ~$0.003.** GPT-4o-mini charges roughly $0.30 per 1,000 fragments. Ten fragments cost less than a penny.

## Step 10: Verify the Graph

Query the graph using Cypher through PostgreSQL:

```bash
python3 -c "
import psycopg2
from build_kg.config import DB_CONFIG, AGE_GRAPH_NAME

conn = psycopg2.connect(**DB_CONFIG)
conn.set_isolation_level(0)
cur = conn.cursor()
cur.execute(\"LOAD 'age';\")
cur.execute(\"SET search_path = ag_catalog, '\$user', public;\")

graph = AGE_GRAPH_NAME

# Count all node types
for label in ['Provision', 'Requirement', 'Constraint']:
    cur.execute(f\"SELECT * FROM cypher('{graph}', \$\$ MATCH (n:{label}) RETURN count(n) \$\$) as (cnt agtype);\")
    print(f'{label}s: {cur.fetchone()[0]}')

# Sample a provision with its requirements
cur.execute(f\"\"\"
    SELECT * FROM cypher('{graph}', \$\$
        MATCH (r:Requirement)-[:DERIVED_FROM]->(p:Provision)
        RETURN p.provision_id, p.authority, r.requirement_type, r.description
        LIMIT 3
    \$\$) as (prov_id agtype, authority agtype, req_type agtype, description agtype);
\"\"\")

print()
print('Sample requirements:')
for row in cur.fetchall():
    print(f'  [{row[0]}] ({row[1]}) {row[2]}: {row[3][:80]}...')

conn.close()
"
```

Expected output:

```
Provisions: 8
Requirements: 18
Constraints: 15

Sample requirements:
  ["B.01.008"] ("Health Canada") "labelling": "Sodium content must be declared per serving on the nutrition facts table"...
  ["UNKNOWN"] ("Health Canada") "labelling": "The ingredient list must appear on the label in descending order of propor"...
  ["B.01.008.2"] ("Health Canada") "composition": "Total fat content must not exceed the prescribed daily value percentage"...
```

## Cost Summary

| Phase | Cost |
|-------|------|
| Crawl (3 pages) | Free |
| Chunk (3 files) | Free |
| Load to DB | Free |
| Parse (10 fragments, sync) | ~$0.003 |
| **Total** | **~$0.003** |

At scale, parsing 1,000 fragments with the batch API costs approximately $0.15.

## Next Steps

- Read the [Architecture](architecture.md) guide to understand the ontology system and pipeline design.
- Follow the [Singapore F&B Tutorial](tutorial-singapore.md) for a full worked example with real regulatory data.
- Use `/build-kg <your topic>` in Claude Code for fully automated graph building with auto-generated ontology.
- See the CLI reference docs for detailed flag descriptions:
  - [Crawler](reference-crawl.md)
  - [Chunker](reference-chunk.md)
  - [Loader](reference-load.md)
  - [Parser](reference-parse.md)
- Check [Troubleshooting](troubleshooting.md) if you hit any errors.
