# Tutorial: Singapore F&B Regulatory Knowledge Graph

This tutorial walks through building a complete knowledge graph of Singapore's food and beverage regulatory landscape. By the end, you will have a graph with approximately 2,400 provisions, 6,000 requirements, and 5,700 constraints drawn from 12 sources across 4 regulatory authorities.

## Overview

Singapore's F&B regulations are issued by multiple authorities:

| Authority | Full Name | Role |
|-----------|-----------|------|
| **SFA** | Singapore Food Agency | Primary food safety regulator. Administers the Sale of Food Act, Food Regulations, and related subsidiary legislation. |
| **Parliament** | Parliament of Singapore | Enacted the Sale of Food Act, Environmental Public Health Act, and other primary legislation. |
| **HPB** | Health Promotion Board | Issues nutrition guidelines, Healthier Choice Symbol programme, and advertising guidelines. |
| **MUIS** | Majlis Ugama Islam Singapura | Islamic Religious Council of Singapore. Administers halal certification and the AMLA. |

## Prerequisites

Complete the [Quickstart Tutorial](tutorial-quickstart.md) first. You should have:

- build-kg installed in a virtual environment
- Docker running with the PostgreSQL + AGE container
- `.env` configured with your Anthropic API key (or OpenAI API key)

## Step 1: Set Up Working Directory

```bash
cd build-kg
source venv/bin/activate

WORK_DIR="./pipelines/reg_sg_fb_$(date +%Y%m%d)"
mkdir -p "$WORK_DIR/crawl_output" "$WORK_DIR/chunk_output"
```

## Step 2: Create the Crawl Manifest

The example manifest at `examples/manifests/singapore-fb.json` lists 12 sources. Copy it into your working directory:

```bash
cp examples/manifests/singapore-fb.json "$WORK_DIR/crawl_manifest.json"
```

If the example file does not exist yet, create the manifest manually. Here is the full manifest for Singapore F&B:

```json
{
  "topic": "Full regulatory compliance landscape of Singapore for F&B",
  "graph_name": "reg_sg_fb",
  "created_at": "2026-02-18T10:00:00Z",
  "sources": [
    {
      "source_name": "sfa_food_regs",
      "url": "https://www.sfa.gov.sg/food-information/legislation",
      "title": "SFA Food Regulations",
      "authority": "SFA",
      "jurisdiction": "SG",
      "doc_type": "regulation",
      "priority": "P1",
      "sub_domains": ["food_safety", "labelling", "additives", "import_export"],
      "depth": 3,
      "max_pages": 100,
      "delay": 2000
    },
    {
      "source_name": "sso_sale_of_food_act",
      "url": "https://sso.agc.gov.sg/Act/SFA1973",
      "title": "Sale of Food Act 1973",
      "authority": "Parliament",
      "jurisdiction": "SG",
      "doc_type": "act",
      "priority": "P1",
      "sub_domains": ["food_safety", "licensing", "enforcement"],
      "depth": 2,
      "max_pages": 50,
      "delay": 2000
    },
    {
      "source_name": "sso_food_regulations",
      "url": "https://sso.agc.gov.sg/SL/SFA1973-RG1",
      "title": "Food Regulations (Cap 283, Rg 1)",
      "authority": "Parliament",
      "jurisdiction": "SG",
      "doc_type": "regulation",
      "priority": "P1",
      "sub_domains": ["labelling", "composition", "additives", "standards"],
      "depth": 2,
      "max_pages": 80,
      "delay": 2000
    },
    {
      "source_name": "sso_ephi_act",
      "url": "https://sso.agc.gov.sg/Act/EPHA1987",
      "title": "Environmental Public Health Act 1987",
      "authority": "Parliament",
      "jurisdiction": "SG",
      "doc_type": "act",
      "priority": "P2",
      "sub_domains": ["food_safety", "licensing", "environmental_health"],
      "depth": 2,
      "max_pages": 40,
      "delay": 2000
    },
    {
      "source_name": "sfa_import_export",
      "url": "https://www.sfa.gov.sg/food-import-export",
      "title": "SFA Import & Export Requirements",
      "authority": "SFA",
      "jurisdiction": "SG",
      "doc_type": "guidance",
      "priority": "P2",
      "sub_domains": ["import_export"],
      "depth": 2,
      "max_pages": 50,
      "delay": 2000
    },
    {
      "source_name": "sfa_food_safety",
      "url": "https://www.sfa.gov.sg/food-information/food-safety-education",
      "title": "SFA Food Safety Guidelines",
      "authority": "SFA",
      "jurisdiction": "SG",
      "doc_type": "guidance",
      "priority": "P2",
      "sub_domains": ["food_safety", "hygiene"],
      "depth": 2,
      "max_pages": 30,
      "delay": 2000
    },
    {
      "source_name": "hpb_nutrition",
      "url": "https://www.hpb.gov.sg/healthy-living/food-beverage",
      "title": "HPB Food & Beverage Guidelines",
      "authority": "HPB",
      "jurisdiction": "SG",
      "doc_type": "guidance",
      "priority": "P2",
      "sub_domains": ["nutrition", "labelling", "advertising"],
      "depth": 2,
      "max_pages": 40,
      "delay": 2000
    },
    {
      "source_name": "hpb_hcs",
      "url": "https://www.hpb.gov.sg/healthy-living/food-beverage/healthier-choice-symbol",
      "title": "HPB Healthier Choice Symbol Programme",
      "authority": "HPB",
      "jurisdiction": "SG",
      "doc_type": "standard",
      "priority": "P2",
      "sub_domains": ["labelling", "claims", "nutrition"],
      "depth": 2,
      "max_pages": 25,
      "delay": 2000
    },
    {
      "source_name": "muis_halal",
      "url": "https://www.muis.gov.sg/Halal/Halal-Certification",
      "title": "MUIS Halal Certification",
      "authority": "MUIS",
      "jurisdiction": "SG",
      "doc_type": "standard",
      "priority": "P2",
      "sub_domains": ["halal"],
      "depth": 2,
      "max_pages": 30,
      "delay": 2000
    },
    {
      "source_name": "sso_amla",
      "url": "https://sso.agc.gov.sg/Act/AMLA1966",
      "title": "Administration of Muslim Law Act",
      "authority": "Parliament",
      "jurisdiction": "SG",
      "doc_type": "act",
      "priority": "P3",
      "sub_domains": ["halal"],
      "depth": 1,
      "max_pages": 25,
      "delay": 2000
    },
    {
      "source_name": "sfa_novel_food",
      "url": "https://www.sfa.gov.sg/food-information/novel-food",
      "title": "SFA Novel Food Framework",
      "authority": "SFA",
      "jurisdiction": "SG",
      "doc_type": "guidance",
      "priority": "P3",
      "sub_domains": ["novel_food"],
      "depth": 1,
      "max_pages": 15,
      "delay": 2000
    },
    {
      "source_name": "sfa_packaging",
      "url": "https://www.sfa.gov.sg/food-information/food-safety/packaging-materials",
      "title": "SFA Food Contact Materials",
      "authority": "SFA",
      "jurisdiction": "SG",
      "doc_type": "guidance",
      "priority": "P3",
      "sub_domains": ["packaging"],
      "depth": 1,
      "max_pages": 15,
      "delay": 2000
    }
  ],
  "defaults": {
    "jurisdiction": "SG",
    "authority": "SFA",
    "doc_type": "regulation"
  },
  "coverage": {
    "covered": [
      "food_safety", "labelling", "nutrition", "additives",
      "import_export", "halal", "novel_food", "packaging",
      "licensing", "environmental_health", "advertising",
      "claims", "composition", "hygiene", "standards",
      "enforcement"
    ],
    "gaps": ["organic", "alcoholic_beverages", "weights_measures"],
    "coverage_pct": 85
  }
}
```

Save this as `$WORK_DIR/crawl_manifest.json`.

## Step 3: Crawl All Sources

Crawl each source from the manifest. This takes approximately 30-60 minutes depending on site response times.

```bash
# Source 1: SFA Food Regulations (P1 - Critical)
build-kg-crawl \
  --url "https://www.sfa.gov.sg/food-information/legislation" \
  --depth 3 --pages 100 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sfa_food_regs/"

# Source 2: Sale of Food Act (P1)
build-kg-crawl \
  --url "https://sso.agc.gov.sg/Act/SFA1973" \
  --depth 2 --pages 50 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sso_sale_of_food_act/"

# Source 3: Food Regulations (Cap 283) (P1)
build-kg-crawl \
  --url "https://sso.agc.gov.sg/SL/SFA1973-RG1" \
  --depth 2 --pages 80 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sso_food_regulations/"

# Source 4: Environmental Public Health Act (P2)
build-kg-crawl \
  --url "https://sso.agc.gov.sg/Act/EPHA1987" \
  --depth 2 --pages 40 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sso_ephi_act/"

# Source 5: SFA Import & Export (P2)
build-kg-crawl \
  --url "https://www.sfa.gov.sg/food-import-export" \
  --depth 2 --pages 50 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sfa_import_export/"

# Source 6: SFA Food Safety Guidelines (P2)
build-kg-crawl \
  --url "https://www.sfa.gov.sg/food-information/food-safety-education" \
  --depth 2 --pages 30 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sfa_food_safety/"

# Source 7: HPB Food & Beverage (P2)
build-kg-crawl \
  --url "https://www.hpb.gov.sg/healthy-living/food-beverage" \
  --depth 2 --pages 40 --delay 2000 \
  --output "$WORK_DIR/crawl_output/hpb_nutrition/"

# Source 8: HPB Healthier Choice Symbol (P2)
build-kg-crawl \
  --url "https://www.hpb.gov.sg/healthy-living/food-beverage/healthier-choice-symbol" \
  --depth 2 --pages 25 --delay 2000 \
  --output "$WORK_DIR/crawl_output/hpb_hcs/"

# Source 9: MUIS Halal Certification (P2)
build-kg-crawl \
  --url "https://www.muis.gov.sg/Halal/Halal-Certification" \
  --depth 2 --pages 30 --delay 2000 \
  --output "$WORK_DIR/crawl_output/muis_halal/"

# Source 10: Administration of Muslim Law Act (P3)
build-kg-crawl \
  --url "https://sso.agc.gov.sg/Act/AMLA1966" \
  --depth 1 --pages 25 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sso_amla/"

# Source 11: SFA Novel Food Framework (P3)
build-kg-crawl \
  --url "https://www.sfa.gov.sg/food-information/novel-food" \
  --depth 1 --pages 15 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sfa_novel_food/"

# Source 12: SFA Food Contact Materials (P3)
build-kg-crawl \
  --url "https://www.sfa.gov.sg/food-information/food-safety/packaging-materials" \
  --depth 1 --pages 15 --delay 2000 \
  --output "$WORK_DIR/crawl_output/sfa_packaging/"
```

After all sources are crawled, optionally clean breadcrumb navigation markers:

```bash
grep -rl "## You are here" "$WORK_DIR/crawl_output/" | while read f; do
  bash src/build_kg/clean.sh "$f"
done
```

Check the total page count:

```bash
find "$WORK_DIR/crawl_output/" -name "*.md" | wc -l
```

Expected: approximately 300-500 markdown files total.

## Step 4: Chunk All Documents

```bash
build-kg-chunk \
  "$WORK_DIR/crawl_output/" \
  "$WORK_DIR/chunk_output/" \
  --strategy by_title \
  --max-chars 1000 \
  --overlap 100
```

Expected: approximately 2,000-3,000 JSON chunk files across all sources. The chunker preserves the directory structure, so chunks for each source are in their own subdirectory.

Check the count:

```bash
find "$WORK_DIR/chunk_output/" -name "*_chunk_*.json" | wc -l
```

## Step 5: Load to Database

Create the graph for Singapore F&B:

```bash
AGE_GRAPH_NAME=reg_sg_fb python -m build_kg.setup_graph
```

Load the chunks:

```bash
build-kg-load "$WORK_DIR/chunk_output/" --manifest "$WORK_DIR/crawl_manifest.json"
```

You can preview what will be loaded first:

```bash
build-kg-load "$WORK_DIR/chunk_output/" --manifest "$WORK_DIR/crawl_manifest.json" --dry-run
```

Expected output:

```
============================================================
  Chunk-to-Database Loader
============================================================
  Manifest: .../crawl_manifest.json
  Sources:  12
  Defaults: jurisdiction=SG, authority=SFA

Scanning chunk files...
  Found 2647 chunks across 387 documents

Processing: sfa_food_regs/legislation_depth0_... (12 chunks)
  Document: a1b2c3d4... (SFA, SG)
  Fragments: 11 inserted

...

============================================================
  LOAD COMPLETE
============================================================
  Documents inserted:  387
  Documents skipped:   0
  Fragments inserted:  2483
  Errors:              0
============================================================
```

## Step 6: Parse with Batch API

With approximately 2,500 fragments, the batch API is recommended. It is 50% cheaper and handles large volumes well.

### 6a: Prepare the Batch

```bash
AGE_GRAPH_NAME=reg_sg_fb build-kg-parse-batch prepare \
  --jurisdiction SG \
  --output sg_fb_batch.jsonl
```

Expected output:

```
======================================================================
Batch Preparation - Step 1
Jurisdiction filter: SG
======================================================================

Fetching fragments (limit=None, offset=0, jurisdiction=SG)...
Found 2483 fragments

Creating batch file: batch_data/sg_fb_batch.jsonl
Processing 2483 fragments...
  Batch file created: batch_data/sg_fb_batch.jsonl
  Metadata saved: batch_data/sg_fb_batch.jsonl.metadata.json

======================================================================
  Batch preparation complete!
Next step: build-kg-parse-batch submit batch_data/sg_fb_batch.jsonl
======================================================================
```

### 6b: Submit the Batch

```bash
build-kg-parse-batch submit batch_data/sg_fb_batch.jsonl
```

Expected output:

```
======================================================================
Batch Submission - Step 2
======================================================================

Uploading file: batch_data/sg_fb_batch.jsonl
  File uploaded: file-abc123...

Creating batch job...
  Batch created: batch_abc123def456
  Status: validating
  Total requests: 2483

  Batch info saved: batch_data/batch_batch_abc123def456.info.json

======================================================================
  Batch submitted successfully!
Batch ID: batch_abc123def456

Monitor progress: build-kg-parse-batch status batch_abc123def456
======================================================================
```

### 6c: Monitor Progress

Check the batch status (one-shot):

```bash
build-kg-parse-batch status batch_abc123def456
```

Or watch until complete (polls every 60 seconds):

```bash
build-kg-parse-batch status batch_abc123def456 --watch
```

Expected output when complete:

```
======================================================================
Batch Status - Step 3
======================================================================

Batch ID: batch_abc123def456
Status: completed
Created: 2026-02-18 14:35:22

Request Counts:
  Total: 2483
  Completed: 2483
  Failed: 0

  Batch completed!
Output file ID: file-xyz789...

Next step: build-kg-parse-batch process batch_abc123def456
======================================================================
```

The batch typically completes in 2-8 hours, but can take up to 24 hours.

### 6d: Process Results into Graph

```bash
AGE_GRAPH_NAME=reg_sg_fb build-kg-parse-batch process batch_abc123def456
```

Expected output:

```
======================================================================
Batch Processing - Step 4
======================================================================
Downloading results for batch batch_abc123def456...
  Results downloaded: batch_data/batch_batch_abc123def456_results.jsonl
Using metadata: sg_fb_batch.jsonl.metadata.json

Processing results from: batch_data/batch_batch_abc123def456_results.jsonl
  Processed 100 provisions...
  Processed 200 provisions...
  ...
  Processed 2400 provisions...

======================================================================
SUMMARY
======================================================================
  Success:  2412
  Failed:   23
  Skipped:  48
======================================================================
```

## Step 7: Validate the Graph

Run validation queries:

```bash
python3 -c "
import psycopg2
from build_kg.config import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
conn.set_isolation_level(0)
cur = conn.cursor()
cur.execute(\"LOAD 'age';\")
cur.execute(\"SET search_path = ag_catalog, '\$user', public;\")

graph = 'reg_sg_fb'

# Count nodes
for label in ['Provision', 'Requirement', 'Constraint']:
    cur.execute(f\"SELECT * FROM cypher('{graph}', \$\$ MATCH (n:{label}) RETURN count(n) \$\$) as (cnt agtype);\")
    print(f'{label}s: {cur.fetchone()[0]}')

# Provisions by authority
cur.execute(f\"\"\"
    SELECT * FROM cypher('{graph}', \$\$
        MATCH (p:Provision)
        RETURN p.authority, count(p)
        ORDER BY count(p) DESC
    \$\$) as (authority agtype, cnt agtype);
\"\"\")
print()
print('By authority:')
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]} provisions')

# Requirements by type
cur.execute(f\"\"\"
    SELECT * FROM cypher('{graph}', \$\$
        MATCH (r:Requirement)
        RETURN r.requirement_type, count(r)
        ORDER BY count(r) DESC
    \$\$) as (req_type agtype, cnt agtype);
\"\"\")
print()
print('By requirement type:')
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')

# ID quality
cur.execute(f\"\"\"
    SELECT * FROM cypher('{graph}', \$\$
        MATCH (p:Provision)
        WHERE p.provision_id = 'UNKNOWN'
        RETURN count(p)
    \$\$) as (cnt agtype);
\"\"\")
unknown = cur.fetchone()[0]
cur.execute(f\"SELECT * FROM cypher('{graph}', \$\$ MATCH (p:Provision) RETURN count(p) \$\$) as (cnt agtype);\")
total = cur.fetchone()[0]
print(f'\\nID quality: {(1 - int(str(unknown)) / max(int(str(total)), 1)) * 100:.1f}% non-UNKNOWN')

conn.close()
"
```

### Expected Final Graph Stats

| Metric | Approximate Count |
|--------|-------------------|
| Provisions | ~2,400 |
| Requirements | ~6,000 |
| Constraints | ~5,700 |
| Provisions by SFA | ~1,200 |
| Provisions by Parliament | ~800 |
| Provisions by HPB | ~250 |
| Provisions by MUIS | ~150 |
| ID quality (non-UNKNOWN) | ~45-65% |

### Sample Queries

Find all labelling requirements from the Food Regulations:

```sql
SELECT * FROM cypher('reg_sg_fb', $$
    MATCH (r:Requirement)-[:DERIVED_FROM]->(p:Provision)
    WHERE r.requirement_type = 'labelling'
      AND p.authority = 'SFA'
    RETURN p.provision_id, r.description, r.deontic_modality
    LIMIT 10
$$) as (prov_id agtype, description agtype, modality agtype);
```

Find threshold constraints on nutritional composition:

```sql
SELECT * FROM cypher('reg_sg_fb', $$
    MATCH (r:Requirement)-[:HAS_CONSTRAINT]->(c:Constraint)
    WHERE c.logic_type = 'threshold'
      AND c.target_signal CONTAINS 'sodium'
    RETURN r.description, c.operator, c.threshold, c.unit
$$) as (desc agtype, op agtype, thresh agtype, unit agtype);
```

Find halal requirements from MUIS:

```sql
SELECT * FROM cypher('reg_sg_fb', $$
    MATCH (r:Requirement)-[:DERIVED_FROM]->(p:Provision)
    WHERE p.authority = 'MUIS'
    RETURN p.provision_id, r.requirement_type, r.description
    LIMIT 10
$$) as (prov_id agtype, req_type agtype, desc agtype);
```

## Cost Breakdown

| Phase | Cost |
|-------|------|
| Crawl (12 sources, ~400 pages) | Free |
| Chunk (~3,000 chunks) | Free |
| Load to DB | Free |
| Parse (2,483 fragments via batch API) | ~$0.37 |
| Graph setup and verification | Free |
| **Total** | **~$3-5** |

The actual cost depends on the length of the regulatory text in each fragment. Longer texts (like the full Food Regulations) consume more tokens. The estimate above assumes an average of ~500 input tokens and ~300 output tokens per fragment at batch API pricing.

If you use the synchronous parser instead, double the parsing cost to approximately $0.75 for 2,500 fragments.

## Tips

- **Government sites often rate-limit.** If you see 403 or timeout errors, increase `--delay` to 3000-5000ms and reduce `--pages`.
- **The Singapore Statutes Online (sso.agc.gov.sg) site** renders legislation dynamically. The crawler's headless Chromium handles this, but you may need to increase the delay.
- **Run a dry-run first** (`build-kg-load --dry-run`) to verify that source matching is correct before committing to the database.
- **Use `--test` mode** on the parser to verify output quality with 5 fragments before committing to a full batch run.
- **ID quality for Singapore** tends to be lower than for Canada or the US because Singapore's statutes use section numbers (e.g., "Section 56") rather than hierarchical IDs (e.g., `B.01.008.2`). This is expected behavior.
