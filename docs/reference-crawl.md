# CLI Reference: build-kg-crawl

Crawl websites and save content as markdown, HTML, or JSON files. Uses Crawl4AI with a headless Chromium browser for JavaScript-rendered pages.

## Usage

```bash
build-kg-crawl --url <URL> [OPTIONS]
```

Or via Python module:

```bash
python -m build_kg.crawl --url <URL> [OPTIONS]
```

## Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--url URL` | `-u URL` | **(required)** | Starting URL to crawl |
| `--delay MS` | `-d MS` | `1000` | Delay between page visits in milliseconds |
| `--format FORMAT` | `-f FORMAT` | `markdown` | Output format: `markdown`, `html`, or `json` |
| `--pages N` | `-p N` | `10` | Maximum number of pages to visit |
| `--depth N` | | `2` | Maximum crawl depth from the start URL |
| `--output DIR` | `-o DIR` | `./output` | Directory to save output files |

## Behavior

### Same-Domain Crawling

The crawler only follows links within the same domain as the start URL. Links to external domains are discovered but not followed. For example, crawling `https://www.sfa.gov.sg/food-information/legislation` will follow links to other `www.sfa.gov.sg` pages but will not crawl links to `sso.agc.gov.sg`.

### Breadth-First Traversal

Pages are crawled in breadth-first order. The start URL is crawled at depth 0. All links discovered on the start page are queued at depth 1, and so on up to `--depth`.

### Deduplication

Each URL is visited at most once. If the same URL is linked from multiple pages, only the first encounter is crawled.

### Output File Naming

Files are named using the URL path, depth, and a timestamp:

```
{path}_depth{N}_{YYYYMMDD_HHMMSS}.{ext}
```

Examples:

```
food-labelling_depth0_20260218_143022.md
regulations_food-safety_depth1_20260218_143025.md
index_depth0_20260218_143022.md
```

The extension is `.md` for markdown, `.html` for HTML, and `.json` for JSON format.

### JSON Output

When `--format json` is used, each file contains:

```json
{
  "url": "https://example.gov/regulations",
  "title": "https://example.gov/regulations",
  "depth": 0,
  "status_code": 200,
  "success": true,
  "markdown": "# Regulations\n\nThis page describes...",
  "html": "<div class=\"content\">...</div>",
  "links": {
    "internal": ["https://example.gov/regulations/food", "..."],
    "external": ["https://other-site.org/reference", "..."]
  },
  "crawled_at": "2026-02-18T14:30:22.123456"
}
```

## Examples

### Basic crawl with defaults

```bash
build-kg-crawl --url "https://www.canada.ca/en/health-canada/services/food-nutrition.html"
```

Crawls up to 10 pages, depth 2, with 1-second delay, saving markdown to `./output/`.

### Crawl a government regulation site

```bash
build-kg-crawl \
  --url "https://sso.agc.gov.sg/Act/SFA1973" \
  --depth 2 \
  --pages 50 \
  --delay 2000 \
  --output ./pipelines/reg_sg_fb/crawl_output/sso_sale_of_food_act/
```

### Crawl with JSON output for debugging

```bash
build-kg-crawl \
  --url "https://www.fda.gov/food/food-labeling-nutrition" \
  --format json \
  --pages 5 \
  --delay 3000 \
  --output ./debug_output/
```

### Large crawl for a primary regulatory source

```bash
build-kg-crawl \
  --url "https://laws-lois.justice.gc.ca/eng/regulations/C.R.C.,_c._870/" \
  --depth 3 \
  --pages 100 \
  --delay 1500 \
  --output ./kg_builds/ca_food_safety/crawled/fdr/
```

## Rate Limiting

Government websites often employ rate limiting or bot detection. If you encounter 403 errors or timeouts:

1. **Increase the delay.** Start with `--delay 2000` (2 seconds). For aggressive rate limiters, try 3000-5000ms.
2. **Reduce the page count.** Fewer concurrent requests are less likely to trigger rate limits.
3. **Try later.** Some government sites have peak-hour throttling.

Recommended delay settings by site type:

| Site Type | Recommended Delay |
|-----------|-------------------|
| Static HTML government pages | 1000-1500ms |
| Singapore Statutes Online (sso.agc.gov.sg) | 2000-3000ms |
| Canada.ca / Justice Laws | 1500-2000ms |
| US FDA / eCFR | 2000-3000ms |
| Sites with Cloudflare / WAF | 3000-5000ms |

## Chromium Requirement

The crawler requires Chromium to render JavaScript-heavy pages. Install it with:

```bash
crawl4ai-setup
```

This downloads a Chromium binary managed by Crawl4AI. If installation fails, check that you have sufficient disk space (~400MB) and that your system supports headless Chromium (most Linux, macOS, and WSL2 environments do).

## Cleaning Crawled Content

Some government websites include breadcrumb navigation (e.g., "## You are here") at the top of every page. The optional `clean.sh` script removes everything above this marker:

```bash
# Clean a single file
bash src/build_kg/clean.sh path/to/file.md

# Clean all files in a crawl output directory
grep -rl "## You are here" ./crawl_output/ | while read f; do
  bash src/build_kg/clean.sh "$f"
done
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Chromium not found" | Run `crawl4ai-setup` |
| 403 Forbidden on every page | Increase `--delay` to 3000-5000ms |
| Timeout on first page | The site may block headless browsers; try a different start URL |
| No internal links found | The site may use JavaScript routing; check if `--format json` shows the HTML content |
| Output directory is empty | Check that the URL is accessible in a normal browser first |
