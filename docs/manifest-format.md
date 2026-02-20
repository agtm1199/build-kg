# Manifest Format

The crawl manifest (`crawl_manifest.json`) is the central configuration file for a build-kg pipeline run. It lists every source to crawl, provides metadata for each source, defines defaults, and tracks coverage.

## Schema Overview

```json
{
  "topic": "string",
  "graph_name": "string",
  "created_at": "ISO 8601 string",
  "sources": [ ... ],
  "defaults": { ... },
  "coverage": { ... },
  "metadata": { ... }
}
```

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `topic` | string | yes | Human-readable description of the topic (e.g., "kubernetes networking" or "Singapore F&B regulations") |
| `graph_name` | string | yes | Apache AGE graph name. Convention: `reg_<country>_<domain>` for regulatory, `kg_<topic>` for generic |
| `created_at` | string | yes | ISO 8601 timestamp of when the manifest was created |
| `sources` | array | yes | List of source objects (see below) |
| `defaults` | object | no | Default metadata applied when a source does not specify a field |
| `coverage` | object | no | Tracks which sub-domains/topics are covered |
| `metadata` | object | no | Arbitrary key-value metadata stored in the `metadata` JSONB column |

## Source Object

Each entry in the `sources` array describes one website to crawl.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_name` | string | yes | Short identifier used as the crawl output directory name (e.g., `sfa_food_regs`, `k8s_docs`). Must be unique within the manifest. This is the key used by the loader for source matching. |
| `url` | string | yes | Starting URL for the crawl |
| `title` | string | yes | Descriptive title of the document or source |
| `authority` | string | no | Issuing organization (e.g., `SFA`, `CFIA`). Nullable for generic topics. |
| `jurisdiction` | string | no | Jurisdiction code from the `market_code` enum. Nullable for generic topics. |
| `doc_type` | string | no | Document type from the `doc_type` enum. Nullable for generic topics. |
| `priority` | string | no | Priority tier: `P1`, `P2`, `P3`, or `P4` |
| `sub_domains` | array | no | List of sub-domain/topic strings this source covers |
| `depth` | integer | no | Crawl depth override (default from priority tier) |
| `max_pages` | integer | no | Maximum pages to crawl override (default from priority tier) |
| `delay` | integer | no | Crawl delay in milliseconds override (default from priority tier) |

### Allowed `jurisdiction` Values

These correspond to the `market_code` PostgreSQL enum:

| Code | Country/Region |
|------|----------------|
| `CA` | Canada |
| `US` | United States |
| `EU` | European Union |
| `UK` | United Kingdom |
| `AU` | Australia |
| `NZ` | New Zealand |
| `JP` | Japan |
| `SG` | Singapore |
| `MY` | Malaysia |
| `TH` | Thailand |
| `KR` | South Korea |
| `CN` | China |
| `IN` | India |
| `AE` | United Arab Emirates |
| `SA` | Saudi Arabia |
| `BR` | Brazil |
| `MX` | Mexico |
| `ZA` | South Africa |
| `OTHER` | Any other jurisdiction |

For generic (non-regulatory) topics, you can omit the `jurisdiction` field entirely.

To add a new jurisdiction, alter the PostgreSQL enum:

```sql
ALTER TYPE market_code ADD VALUE 'XX';
```

### Allowed `doc_type` Values

These correspond to the `doc_type` PostgreSQL enum:

| Value | Description |
|-------|-------------|
| `regulation` | Binding regulatory instrument (subsidiary legislation, rules) |
| `standard` | Technical standard or code of practice |
| `guidance` | Non-binding guidance document, FAQ, or interpretation note |
| `code` | Code of practice or code of conduct |
| `act` | Primary legislation (act of parliament, statute) |
| `directive` | EU-style directive or ministerial directive |
| `order` | Ministerial order, executive order, or gazette notice |

For generic topics, you can omit the `doc_type` field.

### Priority Tiers

Priority tiers provide recommended crawl parameters:

| Tier | Description | Recommended Depth | Recommended Max Pages | Recommended Delay |
|------|-------------|-------------------|-----------------------|-------------------|
| `P1` | Primary authoritative sources | 3 | 100 | 1500ms |
| `P2` | Secondary documentation and standards | 2 | 50 | 1500ms |
| `P3` | Supporting guides, FAQs, tutorials | 1 | 25 | 2000ms |
| `P4` | Reference material, community resources | 1 | 15 | 2000ms |

The `depth`, `max_pages`, and `delay` fields on each source override the tier defaults. If a source does not specify these fields, you should pass the tier defaults to the crawler manually.

## Defaults Object

The `defaults` object provides fallback metadata for chunks that cannot be matched to a specific source.

| Field | Type | Description |
|-------|------|-------------|
| `jurisdiction` | string | Default jurisdiction code (optional for generic topics) |
| `authority` | string | Default authority/organization name (optional for generic topics) |
| `doc_type` | string | Default document type (optional for generic topics) |

Example (regulatory):

```json
"defaults": {
  "jurisdiction": "SG",
  "authority": "SFA",
  "doc_type": "regulation"
}
```

Example (generic):

```json
"defaults": {}
```

When the database loader cannot match a chunk file path to any source's `source_name`, it uses these defaults. A warning is printed for each unmatched document.

## Coverage Object

The `coverage` object tracks which sub-domains or topic areas are addressed by the sources in the manifest. This is used during the source discovery phase to identify gaps.

| Field | Type | Description |
|-------|------|-------------|
| `covered` | array | List of sub-domain strings that have at least one source |
| `gaps` | array | List of sub-domain strings with no source |
| `coverage_pct` | number | Percentage of the sub-domain checklist that is covered |

Example:

```json
"coverage": {
  "covered": [
    "food_safety", "labelling", "nutrition", "additives",
    "import_export", "halal", "novel_food", "packaging"
  ],
  "gaps": ["organic", "alcoholic_beverages", "weights_measures"],
  "coverage_pct": 85
}
```

The sub-domain checklist is defined by the active domain profile. For regulatory profiles, these are regulatory sub-areas (e.g., food safety, labeling, allergens). For generic topics, these are topic-specific areas generated during the ontology phase.

## Generic Topic Example

A manifest for a non-regulatory topic like "kubernetes networking":

```json
{
  "topic": "Kubernetes networking",
  "graph_name": "kg_k8s_net",
  "created_at": "2026-02-20T10:00:00Z",
  "sources": [
    {
      "source_name": "k8s_networking_docs",
      "url": "https://kubernetes.io/docs/concepts/services-networking/",
      "title": "Kubernetes Networking Concepts",
      "priority": "P1",
      "sub_domains": ["services", "ingress", "network_policies"],
      "depth": 3,
      "max_pages": 80,
      "delay": 1500
    },
    {
      "source_name": "cilium_docs",
      "url": "https://docs.cilium.io/en/stable/",
      "title": "Cilium CNI Documentation",
      "priority": "P2",
      "sub_domains": ["cni", "ebpf", "network_policies"],
      "depth": 2,
      "max_pages": 50,
      "delay": 1500
    }
  ],
  "defaults": {},
  "coverage": {
    "covered": ["services", "ingress", "network_policies", "cni", "ebpf"],
    "gaps": ["dns", "load_balancing"],
    "coverage_pct": 70
  }
}
```

Note: `authority`, `jurisdiction`, and `doc_type` are omitted — they are nullable in the database.

## Regulatory Example

```json
{
  "topic": "Full regulatory compliance landscape of Canada for food and beverage",
  "graph_name": "reg_ca_fb",
  "created_at": "2026-02-18T10:00:00Z",
  "sources": [
    {
      "source_name": "fdr",
      "url": "https://laws-lois.justice.gc.ca/eng/regulations/C.R.C.,_c._870/",
      "title": "Food and Drug Regulations (C.R.C., c. 870)",
      "authority": "CFIA",
      "jurisdiction": "CA",
      "doc_type": "regulation",
      "priority": "P1",
      "sub_domains": ["labelling", "composition", "additives", "standards"],
      "depth": 3,
      "max_pages": 100,
      "delay": 1500
    },
    {
      "source_name": "fda",
      "url": "https://laws-lois.justice.gc.ca/eng/acts/F-27/",
      "title": "Food and Drugs Act (R.S.C., 1985, c. F-27)",
      "authority": "Parliament",
      "jurisdiction": "CA",
      "doc_type": "act",
      "priority": "P1",
      "sub_domains": ["food_safety", "enforcement", "prohibition"],
      "depth": 2,
      "max_pages": 50,
      "delay": 1500
    },
    {
      "source_name": "sfcr",
      "url": "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2018-108/",
      "title": "Safe Food for Canadians Regulations",
      "authority": "CFIA",
      "jurisdiction": "CA",
      "doc_type": "regulation",
      "priority": "P1",
      "sub_domains": ["food_safety", "import_export", "licensing", "traceability"],
      "depth": 3,
      "max_pages": 80,
      "delay": 1500
    }
  ],
  "defaults": {
    "jurisdiction": "CA",
    "authority": "CFIA",
    "doc_type": "regulation"
  },
  "coverage": {
    "covered": [
      "food_safety", "labelling", "composition", "additives",
      "import_export", "licensing", "enforcement", "prohibition",
      "standards", "traceability"
    ],
    "gaps": [
      "organic", "halal", "alcoholic_beverages", "novel_food",
      "packaging", "weights_measures"
    ],
    "coverage_pct": 50
  }
}
```

## Manifest Location

The manifest is typically saved in the pipeline working directory:

```
pipelines/
  kg_k8s_net_20260220/           # Generic topic
    crawl_manifest.json
    ontology.yaml                 # Auto-generated ontology
    crawl_output/
      k8s_networking_docs/
      cilium_docs/
    chunk_output/
      k8s_networking_docs/
      cilium_docs/

  reg_sg_fb_20260218/            # Regulatory topic
    crawl_manifest.json
    crawl_output/
      sfa_food_regs/
      sso_sale_of_food_act/
    chunk_output/
      sfa_food_regs/
      sso_sale_of_food_act/
```

Example manifests are available in `examples/manifests/`:
- `singapore-fb.json` -- Singapore F&B regulations (12 sources)
- `canada-food.json` -- Canadian food regulations (3 core sources)

## Creating a Manifest

You can create a manifest in three ways:

1. **Claude Code `/build-kg` skill** (recommended): The skill's Phase 1 (Source Discovery) automatically generates a manifest after researching and presenting sources for approval.
2. **Manually**: Write the JSON file based on your research.
3. **Copy and modify an example**: Start from `examples/manifests/` and adjust URLs and sources for your topic.
