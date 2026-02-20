# CLI Reference: build-kg-load

Load chunked JSON files into the `source_document` and `source_fragment` PostgreSQL tables. This bridges the chunker output to the parser, which reads from these tables. Supports both regulatory sources (with jurisdiction/authority metadata) and generic sources (metadata stored in JSONB).

## Usage

```bash
build-kg-load <chunk_dir> --manifest <path> [OPTIONS]
```

Or via Python module:

```bash
python -m build_kg.load <chunk_dir> --manifest <path> [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `chunk_dir` | Directory containing JSON chunk files (output from `build-kg-chunk`) |

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--manifest PATH` | **(required)** | Path to the `crawl_manifest.json` file with source metadata |
| `--dry-run` | off | Preview what would be inserted without committing to the database |

## How It Works

### 1. Scan Chunks

The loader recursively scans `chunk_dir` for files matching the pattern `*_chunk_*.json`. It groups chunks by their original source filename (from the `metadata.filename` field, or inferred from the chunk filename).

### 2. Match Sources

For each document group, the loader matches the chunk file path to a source entry in the manifest. Matching is done by checking if the `source_name` from the manifest appears in the chunk's file path.

For example, if the manifest has a source with `"source_name": "sfa_food_regs"`, and a chunk file is located at:

```
chunk_output/sfa_food_regs/legislation_depth0_20260218_chunk_1.json
```

The loader matches this chunk to the `sfa_food_regs` source because the string `sfa_food_regs` appears in the file path. This is why the chunker's directory structure preservation is important.

### 3. Apply Metadata

From the matched source entry, the loader extracts:

- `authority` (e.g., `SFA`, `CFIA`) — nullable for generic topics
- `jurisdiction` (e.g., `SG`, `CA`) — nullable for generic topics
- `doc_type` (e.g., `regulation`, `act`, `guidance`) — nullable for generic topics
- `title` and `url`
- `metadata` — arbitrary key-value data stored in the JSONB column

If no source matches, the loader falls back to the `defaults` object in the manifest. For generic (non-regulatory) topics, these fields can be omitted entirely.

### 4. Insert Documents

For each unique source document (grouped by original filename), the loader inserts a row into `source_document`. If a document with the same `filepath` already exists (upsert), the existing row's `updated_at` timestamp is refreshed.

### 5. Insert Fragments

For each chunk within a document, the loader inserts a row into `source_fragment` with:

- `excerpt`: The chunk text (minimum 10 characters; shorter chunks are skipped)
- `context_before`: Last 200 characters of the preceding chunk (for parser context)
- `context_after`: First 200 characters of the following chunk (for parser context)
- `canonical_locator`: Section identifier from chunk metadata, or `{filename}_chunk_{N}` as fallback
- Inherited `jurisdiction`, `authority`, and `doc_type` from the parent document

### 6. Commit

Each document group is committed individually. If one document fails, the error is logged and the loader continues with the next document.

## Examples

### Standard load

```bash
build-kg-load ./chunk_output/ --manifest ./crawl_manifest.json
```

### Preview without committing

```bash
build-kg-load ./chunk_output/ --manifest ./crawl_manifest.json --dry-run
```

Dry-run output:

```
[DRY RUN] Would insert:
  Document: legislation_depth0_20260218_143022
    Authority: SFA, Jurisdiction: SG
    Fragments: 11 (of 12 chunks)
  Document: food-safety_depth1_20260218_143025
    Authority: SFA, Jurisdiction: SG
    Fragments: 7 (of 8 chunks)

  Total: 2 documents, ~20 fragments

[DRY RUN] No data was written.
```

### Load from a specific pipeline run

```bash
build-kg-load \
  ./pipelines/reg_sg_fb_20260218/chunk_output/ \
  --manifest ./pipelines/reg_sg_fb_20260218/crawl_manifest.json
```

## Database Requirements

The loader connects to PostgreSQL using the credentials in `.env` (or environment variables). The following must be in place before running:

1. **Database running**: `docker compose -f db/docker-compose.yml up -d`
2. **Tables created**: The `source_document` and `source_fragment` tables are created by `db/init.sql`, which runs automatically on first container start. If you reset the database, the tables are recreated.
3. **Metadata fields**: The `jurisdiction` and `doc_type` columns are optional TEXT fields. Any string value is accepted. For generic topics, these fields can be omitted from the manifest and will be stored as NULL in the database.

## Source Matching Troubleshooting

If the loader prints "Warning: No manifest match, using defaults" for all documents, check:

1. **Directory structure**: The chunk output must preserve the `source_name` directory from crawling. If you crawled to `crawl_output/sfa_food_regs/` and chunked to `chunk_output/sfa_food_regs/`, the source name `sfa_food_regs` will appear in the path and match correctly.

2. **Manifest source_name**: Ensure each source in the manifest has a `source_name` field that matches the directory name used during crawling.

3. **Case sensitivity**: Source name matching is case-sensitive. Use the exact same casing in the manifest and directory names.

## Output

The loader reports:

```
============================================================
  LOAD COMPLETE
============================================================
  Documents inserted:  12     # New source_document rows
  Documents skipped:   0      # Already existed (upsert)
  Fragments inserted:  2483   # New source_fragment rows
  Errors:              0      # Documents that failed
============================================================
```

After loading, you can verify the data:

```bash
python -m build_kg.verify
```

Or query directly:

```sql
SELECT jurisdiction, authority, COUNT(*)
FROM source_fragment
GROUP BY jurisdiction, authority
ORDER BY COUNT(*) DESC;
```
