# CLI Reference: build-kg-chunk

Chunk markdown and PDF files into JSON fragments using the Unstructured open-source library. Runs entirely locally with no API key required. Works for any topic — regulatory, technical, scientific, or otherwise.

## Usage

```bash
build-kg-chunk <input_dir> <output_dir> [OPTIONS]
```

Or via Python module:

```bash
python -m build_kg.chunk <input_dir> <output_dir> [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `input_dir` | Directory containing input files (markdown and/or PDF). Searched recursively. |
| `output_dir` | Directory to save chunked JSON output files. Created if it does not exist. |

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--strategy STRATEGY` | `by_title` | Chunking strategy: `basic` or `by_title` |
| `--max-chars N` | `1000` | Maximum characters per chunk |
| `--overlap N` | `0` | Number of characters to overlap between consecutive chunks |

## Chunking Strategies

### `by_title` (Recommended)

Respects document structure by starting a new chunk at each heading boundary. Combines small text blocks under headings and splits large sections to stay within the character limit.

Parameters used internally:
- `max_characters`: Set by `--max-chars`
- `new_after_n_chars`: 80% of `--max-chars` (soft target for starting a new chunk)
- `combine_text_under_n_chars`: 100 characters (merge very small blocks)
- `overlap`: Set by `--overlap`

This strategy is recommended for structured documents (regulatory text, technical documentation, specifications) because it preserves section boundaries like numbered sections and headings.

### `basic`

Fills chunks to the maximum character limit without regard for document structure. Useful when the input text has no meaningful headings or when you want uniform chunk sizes.

Parameters used internally:
- `max_characters`: Set by `--max-chars`
- `new_after_n_chars`: 80% of `--max-chars`
- `overlap`: Set by `--overlap`

## Supported File Types

| Extension | Library | Notes |
|-----------|---------|-------|
| `.md` | `unstructured.partition.md` | Included in base install |
| `.pdf` | `unstructured.partition.pdf` | Included with `make setup` |

PDF processing may also require system packages `poppler-utils` and `tesseract-ocr` for OCR-based extraction:

```bash
# Ubuntu/Debian
sudo apt install poppler-utils tesseract-ocr

# macOS
brew install poppler tesseract
```

## Output Format

Each chunk is saved as a separate JSON file named `{original_filename}_chunk_{N}.json`.

### Example Output

For an input file `food-labelling_depth0_20260218_143022.md`, the chunker produces:

```
food-labelling_depth0_20260218_143022_chunk_1.json
food-labelling_depth0_20260218_143022_chunk_2.json
food-labelling_depth0_20260218_143022_chunk_3.json
...
```

Each JSON file has this structure:

```json
{
  "text": "The nutrition facts table must include the following information: energy value in calories and kilojoules, protein, total fat, saturated fat, trans fat, cholesterol, sodium, total carbohydrate, dietary fibre, sugars, and any vitamins or minerals present in significant amounts.",
  "type": "CompositeElement",
  "metadata": {
    "filename": "food-labelling_depth0_20260218_143022.md",
    "filetype": "text/markdown",
    "languages": ["eng"],
    "page_number": 1,
    "source_file_path": "/crawl_output/hc_labelling/food-labelling_depth0_20260218_143022.md",
    "chunking_date": "2026-02-18 14:35:00",
    "chunking_strategy": "by_title",
    "max_characters": 1000,
    "chunk_index": 3,
    "total_chunks": 8,
    "chunk_position": "middle",
    "fingerprint": "a1b2c3d4e5f6..."
  }
}
```

### Metadata Fields

| Field | Description |
|-------|-------------|
| `filename` | Original source filename |
| `filetype` | MIME type of the source file |
| `languages` | Detected languages |
| `page_number` | Page number in the source document (for PDFs) |
| `source_file_path` | Path to the source file, including up to 2 parent directories |
| `chunking_date` | Timestamp when chunking was performed |
| `chunking_strategy` | Strategy used (`basic` or `by_title`) |
| `max_characters` | Maximum character limit that was configured |
| `chunk_index` | 1-based index of this chunk within the document |
| `total_chunks` | Total number of chunks for this document |
| `chunk_position` | Position within the document: `first`, `middle`, `last`, or `only` |
| `fingerprint` | SHA-256 hash of normalized text (for deduplication) |
| `coordinates` | Bounding box coordinates (PDFs only, when available) |
| `detection_class_prob` | Element detection confidence scores (PDFs only, when available) |

## Directory Structure Preservation

The chunker preserves the directory structure of the input. If the input directory looks like:

```
crawl_output/
  sfa_food_regs/
    legislation_depth0_20260218.md
    food-safety_depth1_20260218.md
  hpb_nutrition/
    food-beverage_depth0_20260218.md
```

The output directory will mirror this:

```
chunk_output/
  sfa_food_regs/
    legislation_depth0_20260218_chunk_1.json
    legislation_depth0_20260218_chunk_2.json
    food-safety_depth1_20260218_chunk_1.json
  hpb_nutrition/
    food-beverage_depth0_20260218_chunk_1.json
    food-beverage_depth0_20260218_chunk_2.json
```

This structure is important because the database loader uses the directory name to match chunks to their source entry in the crawl manifest.

## Examples

### Standard chunking for structured documents

```bash
build-kg-chunk ./crawl_output/ ./chunk_output/ --strategy by_title --max-chars 1000
```

### Chunking with overlap for better context

```bash
build-kg-chunk ./crawl_output/ ./chunk_output/ --strategy by_title --max-chars 1000 --overlap 100
```

### Basic chunking for unstructured text

```bash
build-kg-chunk ./crawl_output/ ./chunk_output/ --strategy basic --max-chars 500
```

### Chunking PDF documents

```bash
build-kg-chunk ./pdf_documents/ ./chunk_output/ --strategy by_title --max-chars 1200
```

## Choosing max-chars

| Fragment Length | Trade-off |
|----------------|-----------|
| 500 chars | More chunks, more granular, higher parsing cost |
| 1000 chars (default) | Good balance for most document types |
| 1500-2000 chars | Fewer chunks, cheaper parsing, but may mix multiple topics per chunk |

For most text, 1000 characters typically captures one coherent section or subsection. This is the recommended default.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No PDF or MD files found" | Check that the input directory contains `.md` or `.pdf` files (the search is recursive) |
| "PDF support not installed" | Run `make setup` to install all dependencies including PDF support |
| PDF chunking fails with OCR errors | Install `poppler-utils` and `tesseract-ocr` system packages |
| Very small chunks (< 50 chars) | These are filtered out by the database loader (min 10 chars) and parser (min 50 chars) |
| "Unsupported file type" | Only `.md` and `.pdf` are supported. Convert other formats to markdown first. |
